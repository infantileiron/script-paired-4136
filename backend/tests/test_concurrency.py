import threading

import pytest

from src.config.database import Session
from src.models.entities import AnonRelease, PrivacyBudget, PrivacyLedger
from src.services import publish
from src.services.privacy import TOTAL_EPSILON
from tests.factories import make_pair, make_evaluation, make_budgets


def test_concurrent_requests_never_overspend_shared_consultant(session, artifact_dir):
    # 5 个并发申请，每个名单都含共享顾问 SHARED；每次 ε=1.0，上限 4.0 -> 仅 4 个可成功
    n_requests = 5
    epsilon = 1.0
    shared = make_pair(session, 'SHARED', before=70, after=80)
    evs = []
    for k in range(n_requests):
        others = [make_pair(session, f'E{k}-{i}', before=70, after=73) for i in range(2)]
        ev = make_evaluation(session, name=f'ev{k}', pairs=others + [shared])
        evs.append(ev)
    session.commit()

    all_codes = set()
    roster_by_ev = {}
    for ev in evs:
        codes = publish.fixed_roster(session, ev.id)[1]
        roster_by_ev[ev.id] = codes
        all_codes.update(codes)
    make_budgets(session, sorted(all_codes))
    session.commit()

    release_ids = []
    for ev in evs:
        r = AnonRelease(evaluation_id=ev.id, name='c', state='pending',
                        roster=roster_by_ev[ev.id], lower=-20, upper=20, epsilon=epsilon,
                        attempts=0, created=publish.now_iso(), updated=publish.now_iso())
        session.add(r)
        session.commit()
        release_ids.append(r.id)

    errors = []
    barrier = threading.Barrier(n_requests)

    def worker(rid):
        try:
            barrier.wait(timeout=15)  # 让所有线程同时进入，最大化争抢
            with Session() as s:
                publish.process_release(s, rid)
        except BaseException as e:  # pragma: no cover - 仅用于捕获线程内异常
            errors.append((rid, repr(e)))

    threads = [threading.Thread(target=worker, args=(rid,)) for rid in release_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors
    # worker 用独立会话提交；这里必须用全新会话读取已提交状态，避免当前会话的陈旧身份映射
    with Session() as verify:
        states = [verify.get(AnonRelease, rid).state for rid in release_ids]
        assert states.count('downloadable') == 4   # 受 4.0 累计预算限制
        assert states.count('failed') == 1         # 超额的整次拒绝
        assert 'pending' not in states             # 没有申请被卡住

        shared_row = verify.query(PrivacyBudget).filter_by(
            consultant_code='SHARED').one()
        # 绝不透支：累计扣账严格不超过上限
        assert shared_row.spent_epsilon <= TOTAL_EPSILON + 1e-12
        assert shared_row.spent_epsilon == pytest.approx(4.0)

        # 成功申请各有一份流水，失败申请没有任何流水（整次拒绝）
        for rid in release_ids:
            cnt = verify.query(PrivacyLedger).filter_by(release_id=rid).count()
            state = verify.get(AnonRelease, rid).state
            roster_len = len(verify.get(AnonRelease, rid).roster)
            if state == 'downloadable':
                assert cnt == roster_len
            else:
                assert cnt == 0

        # 任何账户都不允许出现负余额或超额
        for b in verify.query(PrivacyBudget).all():
            assert b.spent_epsilon <= b.total_epsilon + 1e-12
            assert b.spent_epsilon >= -1e-12
