import pytest

from src.services import publish
from tests.factories import make_pair, make_evaluation, make_budgets, spend
from src.models.entities import AnonRelease, PrivacyBudget
from src.services.privacy import TOTAL_EPSILON


def _release(s, ev, codes, lower=-20.0, upper=20.0, epsilon=1.0):
    r = AnonRelease(evaluation_id=ev.id, name='r', state='pending', roster=codes,
                    lower=lower, upper=upper, epsilon=epsilon, attempts=0,
                    created=publish.now_iso(), updated=publish.now_iso())
    s.add(r)
    s.commit()
    return r


def test_fixed_roster_uses_frozen_snapshot_complete_pairs_only(session):
    p1 = make_pair(session, 'C1', before=70, after=75)
    p2 = make_pair(session, 'C2', before=None, after=80)   # 缺前测 -> 排除
    p3 = make_pair(session, 'C3', before=60, after=None)   # 缺后测 -> 排除
    p4 = make_pair(session, 'C4', before=65, after=70)
    ev = make_evaluation(session, pairs=[p1, p2, p3, p4])
    session.commit()
    _, codes = publish.fixed_roster(session, ev.id)
    assert codes == ['C1', 'C4']  # 仅完整配对，且按编号排序固定


def test_fixed_roster_requires_done_evaluation(session):
    p1 = make_pair(session, 'C1')
    ev = make_evaluation(session, state='queued', pairs=[p1])
    session.commit()
    with pytest.raises(ValueError):
        publish.fixed_roster(session, ev.id)


def test_fixed_roster_missing_evaluation(session):
    with pytest.raises(LookupError):
        publish.fixed_roster(session, 999)


def test_overlapping_rosters_share_cumulative_budget(session, artifact_dir):
    # 两组评估共享同一位顾问 C2：跨评估发布都要在 C2 的累计预算上扣账
    g1 = [make_pair(session, f'A{i}', team='企业一组', before=70, after=72) for i in range(3)]
    g2 = [make_pair(session, f'B{i}', team='企业二组', before=70, after=72) for i in range(3)]
    shared = make_pair(session, 'C2', team='企业二组', before=70, after=80)
    ev1 = make_evaluation(session, name='组1', pairs=g1 + [shared])
    ev2 = make_evaluation(session, name='组2', pairs=g2 + [shared])
    session.commit()
    codes1 = publish.fixed_roster(session, ev1.id)[1]
    codes2 = publish.fixed_roster(session, ev2.id)[1]
    assert 'C2' in codes1 and 'C2' in codes2  # 重叠名单
    make_budgets(session, sorted(set(codes1 + codes2)))
    session.commit()

    eps = 1.5
    r1 = _release(session, ev1, codes1, epsilon=eps)
    assert publish.process_release(session, r1.id) == 'downloadable'
    r2 = _release(session, ev2, codes2, epsilon=eps)
    assert publish.process_release(session, r2.id) == 'downloadable'

    c2 = session.query(PrivacyBudget).filter_by(consultant_code='C2').one()
    # 共享顾问被扣两次，累计而非每次重置
    assert c2.spent_epsilon == pytest.approx(2 * eps)
    only_one = session.query(PrivacyBudget).filter_by(consultant_code='A0').one()
    assert only_one.spent_epsilon == pytest.approx(eps)


def test_over_budget_rejects_whole_request_without_partial_charge(session, artifact_dir):
    pairs = [make_pair(session, f'C{i}', before=70, after=72) for i in range(4)]
    ev = make_evaluation(session, pairs=pairs)
    session.commit()
    codes = publish.fixed_roster(session, ev.id)[1]
    make_budgets(session, codes)
    # 让其中一位顾问预算即将用尽：剩余 0.4，而本次申请要 1.0
    spend(session, 'C1', TOTAL_EPSILON - 0.4)
    session.commit()

    r = _release(session, ev, codes, epsilon=1.0)
    assert publish.process_release(session, r.id) == 'failed'
    session.refresh(r)
    assert r.state == 'failed' and '预算不足' in r.error

    # 整次拒绝：名单内任何人都不应被扣款
    spent_map = {b.consultant_code: b.spent_epsilon for b in session.query(PrivacyBudget).all()}
    assert spent_map['C1'] == pytest.approx(TOTAL_EPSILON - 0.4)
    assert spent_map['C0'] == 0.0 and spent_map['C2'] == 0.0 and spent_map['C3'] == 0.0
    # 没有产物、没有流水
    import os
    assert not os.path.exists(os.path.join(artifact_dir, f'anon-release-{r.id}.json'))
    from src.models.entities import PrivacyLedger
    assert session.query(PrivacyLedger).filter_by(release_id=r.id).count() == 0


def test_exact_cap_is_allowed_over_cap_rejected(session, artifact_dir):
    pairs = [make_pair(session, f'C{i}', before=70, after=72) for i in range(2)]
    ev = make_evaluation(session, pairs=pairs)
    session.commit()
    codes = publish.fixed_roster(session, ev.id)[1]
    make_budgets(session, codes)
    spend(session, 'C0', TOTAL_EPSILON - 1.0)  # 恰好剩 1.0
    session.commit()
    r = _release(session, ev, codes, epsilon=1.0)
    assert publish.process_release(session, r.id) == 'downloadable'  # 等于上限允许
    row = session.query(PrivacyBudget).filter_by(consultant_code='C0').one()
    assert row.spent_epsilon == pytest.approx(TOTAL_EPSILON)
