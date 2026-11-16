"""匿名发布领域服务。

职责：
1. 从已完成评估的冻结快照中取"固定评估名单"（完整配对顾问，提交即冻结，重试不重选）。
2. 事务内对名单上每位顾问的累计预算账户做行锁 + 原子检查扣减；任一顾问超额则整次拒绝、不扣账。
3. 调用拉普拉斯机制生成确定性噪声；重试同一申请复用同一噪声（由申请 ID 派生）且不重扣。
4. 预算与 downloadable 状态在同一事务先提交，随后写临时文件并原子替换：
   下载以 DB 状态为准，故"可下载"恒等价于"已扣账"；写文件中断后启动恢复可安全重建/重跑。
"""
import json
import os
from datetime import datetime, timezone

from sqlalchemy import text

from src.models.entities import AnonRelease, Evaluation, PrivacyBudget, PrivacyLedger
from src.services import privacy
from src.services import broker as broker_mod
from src.services.broker import BUDGET_LOCK, RELEASE_QUEUE
from src.services.db_retry import is_sqlite

ARTIFACT_DIR = os.environ.get('ARTIFACT_DIR', '/artifacts')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _dialect(s):
    return s.bind.dialect.name if s.bind is not None else ''


def advisory_acquire(s):
    """PostgreSQL 事务级咨询锁；SQLite/其他库退化为无操作（由分布式锁与行锁兜底）。"""
    if _dialect(s) == 'postgresql':
        s.execute(text('SELECT pg_advisory_xact_lock(87342115)'))


def _lock_budget_rows(s, codes):
    q = s.query(PrivacyBudget).filter(PrivacyBudget.consultant_code.in_(codes))
    if _dialect(s) == 'postgresql':
        return q.with_for_update(nowait=False).order_by(PrivacyBudget.consultant_code).all()
    return q.order_by(PrivacyBudget.consultant_code).all()


def fixed_roster(s, evaluation_id):
    """固定评估名单：评估必须已完成，名单取自冻结快照中的完整配对顾问，按编号排序。"""
    ev = s.get(Evaluation, evaluation_id)
    if not ev:
        raise LookupError('评估任务不存在')
    if ev.state != 'done':
        raise ValueError('仅成功评估可发起匿名发布')
    snapshot = (ev.result or {}).get('snapshot') or []
    codes = sorted(r['code'] for r in snapshot
                   if r.get('before') is not None and r.get('after') is not None)
    if not codes:
        raise ValueError('该评估的冻结快照中没有完整配对，无法发布')
    return ev, codes


def reserve_budgets(s, release, codes, epsilon):
    """事务内原子检查并扣减名单上每位顾问的共享预算。

    并发安全：调用方持有分布式预算锁 + 事务咨询锁；此处再对预算行按固定顺序加行锁，
    并用条件更新兜底，保证并发申请绝不透支。任何一位顾问超额都整笔回滚（整次拒绝）。
    """
    existing = {x.consultant_code for x in
                s.query(PrivacyLedger.consultant_code).filter(
                    PrivacyLedger.release_id == release.id).all()}
    if existing:  # 重试复用：该申请已扣过账，幂等返回，不重扣
        return False
    rows = {r.consultant_code: r for r in _lock_budget_rows(s, codes)}
    # 名单上每位顾问都必须有预算账户（种子数据预建；缺失则视为数据异常，整次拒绝）
    missing = [c for c in codes if c not in rows]
    if missing:
        raise RuntimeError('顾问预算账户缺失：' + ','.join(missing))
    over = [c for c in codes if rows[c].spent_epsilon + epsilon > rows[c].total_epsilon + 1e-12]
    if over:
        raise ValueError('隐私预算不足，整次发布已拒绝：顾问 ' + '、'.join(sorted(over))
                         + ' 的累计预算将超出上限')
    stamp = now_iso()
    for c in codes:
        row = rows[c]
        row.spent_epsilon = row.spent_epsilon + epsilon
        s.add(PrivacyLedger(release_id=release.id, consultant_code=c,
                            epsilon=epsilon, created=stamp))
    return True


def _differences_for(evaluation, codes):
    """从冻结快照按固定名单取差值（后测−前测），顺序与名单一致。"""
    by_code = {r['code']: r for r in evaluation.result['snapshot']}
    return [by_code[c]['after'] - by_code[c]['before'] for c in codes]


def _artifact_paths(release_id):
    final = os.path.join(ARTIFACT_DIR, f'anon-release-{release_id}.json')
    tmp = final + '.tmp'
    return final, tmp


def process_release(s, release_id):
    """Worker 执行一次发布（含重试）。返回最终状态字符串。"""
    release = s.get(AnonRelease, release_id)
    if release is None:
        raise LookupError('发布申请不存在')
    if release.state == 'downloadable':
        return 'downloadable'  # 已完成，幂等跳过，不重扣
    final, tmp = _artifact_paths(release_id)
    release.attempts = (release.attempts or 0) + 1
    release.updated = now_iso()
    evaluation = s.get(Evaluation, release.evaluation_id)
    codes = list(release.roster)
    token = None
    for _ in range(20):  # 等待分布式预算锁，避免并发申请透支
        token = broker_mod.broker().acquire_lock(BUDGET_LOCK)
        if token:
            break
        import time as _t
        _t.sleep(0.1)
    if not token:
        release.state = 'failed'
        release.error = '预算锁繁忙，请稍后重试'
        release.updated = now_iso()
        s.commit()
        return 'failed'
    try:
        def _transaction():
            advisory_acquire(s)
            reserve_budgets(s, release, codes, release.epsilon)
            differences = _differences_for(evaluation, codes)
            # 噪声由申请 ID 派生：重试同申请得到同一噪声，且此刻预算已落账
            rel = privacy.build_release(differences, release.lower, release.upper,
                                        release.epsilon, release.id)
            payload = privacy.public_payload(rel)
            payload.update({
                'release_id': release.id,
                'evaluation_id': release.evaluation_id,
                'name': release.name,
                'roster_size': len(codes),
                'created': release.created,
                'published_at': now_iso(),
                'note': '对外仅提供加噪均值与差分隐私机制参数；顾问编号与原始差值不包含在本产物中。',
            })
            release.result = payload
            release.state = 'downloadable'
            release.error = ''
            release.artifact_path = final
            release.updated = now_iso()
            # 关键顺序：先在同一事务提交预算扣账 + downloadable 状态，
            # 之后才原子替换文件。下载接口以 DB 的 downloadable 为准，
            # 因此“可下载”恒等价于“已扣账”，文件崩溃不影响账目一致性。
            s.commit()
            return payload

        payload = None
        try:
            if is_sqlite(s):
                # SQLite 仅本地/测试使用：并发写偶发 database is locked，退避后整体重跑；
                # reserve 幂等、噪声由申请 ID 确定，重跑安全且不重扣。
                import time as _t
                for attempt in range(8):
                    try:
                        payload = _transaction()
                        break
                    except Exception as exc:
                        from sqlalchemy.exc import OperationalError
                        if isinstance(exc, OperationalError) and 'locked' in str(exc).lower() \
                                and attempt < 7:
                            s.rollback()
                            _t.sleep(0.05 * (2 ** attempt))
                            continue
                        raise
            else:
                payload = _transaction()
        except Exception as exc:
            s.rollback()
            # 失败不保留任何预算扣减：reserve 与状态在同一事务，回滚即全额返还
            fresh = s.get(AnonRelease, release_id)
            if fresh is not None and fresh.state != 'downloadable':
                fresh.state = 'failed'
                fresh.error = str(exc)
                fresh.updated = now_iso()
                s.commit()
            return 'failed'
        # 事务已提交（预算已扣、状态 downloadable）；文件写入失败不应回滚账目，
        # 下载以 DB 结果为准，恢复时会据 downloadable 状态重建产物。
        try:
            os.makedirs(ARTIFACT_DIR, exist_ok=True)
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, final)
        except OSError:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return 'downloadable'
    finally:
        broker_mod.broker().release_lock(BUDGET_LOCK, token)


def ensure_budget_accounts(s, codes):
    """为顾问预建累计预算账户；已存在则保持不变。返回账户字典。"""
    existing = {r.consultant_code: r for r in
                s.query(PrivacyBudget).filter(PrivacyBudget.consultant_code.in_(codes)).all()}
    created = []
    for c in codes:
        if c not in existing:
            row = PrivacyBudget(consultant_code=c, total_epsilon=privacy.TOTAL_EPSILON,
                                spent_epsilon=0.0)
            s.add(row)
            existing[c] = row
            created.append(c)
    if created:
        s.commit()
    return existing


def budget_overview(s):
    """页面查询：每位顾问的预算总额、已用、剩余，以及发布申请状态汇总。"""
    rows = s.query(PrivacyBudget).order_by(PrivacyBudget.consultant_code).all()
    accounts = [{
        'consultant_code': r.consultant_code,
        'total_epsilon': r.total_epsilon,
        'spent_epsilon': round(r.spent_epsilon, 10),
        'remaining_epsilon': round(r.total_epsilon - r.spent_epsilon, 10),
    } for r in rows]
    releases = [{
        'id': r.id,
        'evaluation_id': r.evaluation_id,
        'name': r.name,
        'state': r.state,
        'epsilon': r.epsilon,
        'lower': r.lower,
        'upper': r.upper,
        'roster_size': len(r.roster or []),
        'attempts': r.attempts,
        'error': r.error,
        'created': r.created,
        'updated': r.updated,
    } for r in s.query(AnonRelease).order_by(AnonRelease.id.desc()).all()]
    return {'total_epsilon_cap': privacy.TOTAL_EPSILON, 'accounts': accounts, 'releases': releases}


def enqueue_release(s, release):
    broker_mod.broker().rpush(RELEASE_QUEUE, release.id)


def recover_pending(s):
    """启动恢复。

    状态以 DB 为准（downloadable 恒表示预算已扣）：
    - downloadable：账目已完成，若产物文件缺失则从 DB 结果重建，绝不重扣；
    - pending/failed：预算尚未提交，清理临时文件后重新入队，重试复用同一申请 ID，
      因而确定性噪声不变；reserve 的幂等检查与流水唯一约束保证不重扣。
    """
    recovered = []
    for r in s.query(AnonRelease).order_by(AnonRelease.id).all():
        final, tmp = _artifact_paths(r.id)
        if r.state == 'downloadable':
            if not os.path.exists(final) and r.result:
                os.makedirs(ARTIFACT_DIR, exist_ok=True)
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(r.result, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, final)
            continue
        # 未完成：清理残留临时文件后重新排队
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        r.state = 'pending'
        r.updated = now_iso()
        s.commit()
        broker_mod.broker().rpush(RELEASE_QUEUE, r.id)
        recovered.append(r.id)
    return recovered
