import json
import os

import pytest

from src.models.entities import AnonRelease, PrivacyBudget, PrivacyLedger
from src.services import privacy, publish
from tests.factories import make_pair, make_evaluation, make_budgets


def _setup(session, n=4):
    pairs = [make_pair(session, f'C{i}', before=70, after=72 + i) for i in range(n)]
    ev = make_evaluation(session, pairs=pairs)
    session.commit()
    codes = publish.fixed_roster(session, ev.id)[1]
    make_budgets(session, codes)
    session.commit()
    r = AnonRelease(evaluation_id=ev.id, name='r', state='pending', roster=codes,
                    lower=-20, upper=20, epsilon=1.0, attempts=0,
                    created=publish.now_iso(), updated=publish.now_iso())
    session.add(r)
    session.commit()
    return ev, r, codes


def test_retry_reuses_same_noise_and_charges_once(session, artifact_dir):
    ev, r, codes = _setup(session)
    assert publish.process_release(session, r.id) == 'downloadable'
    first = dict(session.get(AnonRelease, r.id).result)
    noise_first = privacy.deterministic_noise(r.id, r.epsilon,
                                              privacy.sensitivity_for(len(codes), -20, 20))

    # 模拟失败后人工重试：状态回到 pending 再处理
    r2 = session.get(AnonRelease, r.id)
    r2.state = 'pending'
    session.commit()
    assert publish.process_release(session, r2.id) == 'downloadable'

    second = session.get(AnonRelease, r.id).result
    # 同一申请 ID -> 同一噪声 -> 同一加噪均值
    assert second['noisy_mean'] == first['noisy_mean']
    assert privacy.deterministic_noise(r.id, r.epsilon,
                                       privacy.sensitivity_for(len(codes), -20, 20)) == noise_first

    # 每位顾问只有一条流水，只扣一次 ε
    ledgers = session.query(PrivacyLedger).filter_by(release_id=r.id).all()
    assert len(ledgers) == len(codes)
    for b in session.query(PrivacyBudget).all():
        assert b.spent_epsilon == pytest.approx(1.0)


def test_process_is_idempotent_when_already_downloadable(session, artifact_dir):
    _, r, codes = _setup(session)
    assert publish.process_release(session, r.id) == 'downloadable'
    # 再次处理（队列重复投递）应直接幂等返回，不增加 attempts 之外的扣账
    before = {b.consultant_code: b.spent_epsilon for b in session.query(PrivacyBudget).all()}
    assert publish.process_release(session, r.id) == 'downloadable'
    after = {b.consultant_code: b.spent_epsilon for b in session.query(PrivacyBudget).all()}
    assert before == after
    assert session.query(PrivacyLedger).filter_by(release_id=r.id).count() == len(codes)


def test_recovery_rebuilds_file_when_downloadable_but_file_lost(session, artifact_dir):
    _, r, _ = _setup(session)
    assert publish.process_release(session, r.id) == 'downloadable'
    final, _ = publish._artifact_paths(r.id)
    assert os.path.exists(final)
    os.remove(final)  # 模拟文件卷丢失/写后被清理，但 DB 已 committed（已扣账）

    recovered = publish.recover_pending(session)
    assert r.id not in recovered  # downloadable 不会重新入队、不重扣
    assert os.path.exists(final)  # 从 DB 结果重建产物
    rebuilt = json.loads(open(final, encoding='utf-8').read())
    assert rebuilt['release_id'] == r.id
    assert 'noisy_mean' in rebuilt and 'clipped_mean' not in rebuilt
    # 预算仍是单次扣账
    for b in session.query(PrivacyBudget).all():
        assert b.spent_epsilon == pytest.approx(1.0)


def test_recovery_requeues_pending_and_cleans_tmp(session, artifact_dir, monkeypatch):
    _, r, codes = _setup(session)
    final, tmp = publish._artifact_paths(r.id)
    # 模拟写文件中断：留下 .tmp，状态仍是 pending（预算尚未提交）
    os.makedirs(artifact_dir, exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('partial')
    assert session.query(PrivacyLedger).filter_by(release_id=r.id).count() == 0

    recovered = publish.recover_pending(session)
    assert recovered == [r.id]
    assert not os.path.exists(tmp)                 # 临时文件被清理
    assert session.get(AnonRelease, r.id).state == 'pending'

    # 恢复后正常处理成功，噪声仍由同一申请 ID 确定性生成
    assert publish.process_release(session, r.id) == 'downloadable'
    assert os.path.exists(final)
    for b in session.query(PrivacyBudget).all():
        assert b.spent_epsilon == pytest.approx(1.0)


def test_recovery_after_failed_then_retry_succeeds(session, artifact_dir):
    pairs = [make_pair(session, f'C{i}', before=70, after=72) for i in range(3)]
    ev = make_evaluation(session, pairs=pairs)
    session.commit()
    codes = publish.fixed_roster(session, ev.id)[1]
    make_budgets(session, codes)
    # 先把预算耗尽使首次发布失败
    from tests.factories import spend
    from src.services.privacy import TOTAL_EPSILON
    for c in codes:
        spend(session, c, TOTAL_EPSILON)
    session.commit()
    r = AnonRelease(evaluation_id=ev.id, name='r', state='pending', roster=codes,
                    lower=-20, upper=20, epsilon=1.0, attempts=0,
                    created=publish.now_iso(), updated=publish.now_iso())
    session.add(r)
    session.commit()
    assert publish.process_release(session, r.id) == 'failed'
    assert session.query(PrivacyLedger).filter_by(release_id=r.id).count() == 0

    # 预算恢复（例如管理员调整）后重试，同一申请成功
    for b in session.query(PrivacyBudget).all():
        b.spent_epsilon = 0.0
    session.commit()
    r.state = 'pending'
    session.commit()
    assert publish.process_release(session, r.id) == 'downloadable'
    assert session.query(PrivacyLedger).filter_by(release_id=r.id).count() == len(codes)
