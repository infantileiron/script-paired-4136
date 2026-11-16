import os

from src.config.database import Session
from src.models.entities import AnonRelease, PrivacyBudget, PrivacyLedger
from src.services import publish
from src.services.broker import RELEASE_QUEUE, broker
from src import worker
from tests.factories import make_pair, make_evaluation, make_budgets


def _make_pending(session):
    pairs = [make_pair(session, f'C{i}', before=70, after=72 + i) for i in range(4)]
    ev = make_evaluation(session, pairs=pairs)
    session.commit()
    codes = publish.fixed_roster(session, ev.id)[1]
    make_budgets(session, codes)
    session.commit()
    r = AnonRelease(evaluation_id=ev.id, name='q', state='pending', roster=codes,
                    lower=-20, upper=20, epsilon=1.0, attempts=0,
                    created=publish.now_iso(), updated=publish.now_iso())
    session.add(r)
    session.commit()
    return r, codes


def test_worker_consumes_release_queue(session, artifact_dir):
    r, codes = _make_pending(session)
    broker().rpush(RELEASE_QUEUE, r.id)
    item = broker().blpop(RELEASE_QUEUE, timeout=2)
    assert item is not None
    worker._handle_release(item[1])
    with Session() as s:
        assert s.get(AnonRelease, r.id).state == 'downloadable'
        assert s.query(PrivacyLedger).filter_by(release_id=r.id).count() == len(codes)
    assert os.path.exists(os.path.join(artifact_dir, f'anon-release-{r.id}.json'))


def test_worker_startup_recovery_requeues_pending(session, artifact_dir):
    r, _ = _make_pending(session)
    # 不直接入队，模拟 worker 重启时库里仍有 pending：_recover 应重新入队并处理
    worker._recover()
    item = broker().blpop(RELEASE_QUEUE, timeout=2)
    assert item is not None and int(item[1]) == r.id
    worker._handle_release(item[1])
    with Session() as s:
        assert s.get(AnonRelease, r.id).state == 'downloadable'
    # 恢复幂等：再次启动不会重复扣账
    worker._recover()
    assert broker().blpop(RELEASE_QUEUE, timeout=1) is None
    with Session() as s:
        assert s.query(PrivacyLedger).filter_by(release_id=r.id).count() == 4
        for b in s.query(PrivacyBudget).all():
            assert b.spent_epsilon == 1.0


def test_worker_recovery_rebuilds_lost_file_without_recharge(session, artifact_dir):
    r, _ = _make_pending(session)
    worker._recover()
    item = broker().blpop(RELEASE_QUEUE, timeout=2)
    worker._handle_release(item[1])
    final, _ = publish._artifact_paths(r.id)
    os.remove(final)
    # 重启恢复：downloadable 但文件丢失 -> 仅重建文件，不产生队列任务、不重扣
    worker._recover()
    assert broker().blpop(RELEASE_QUEUE, timeout=1) is None
    assert os.path.exists(final)
    with Session() as s:
        for b in s.query(PrivacyBudget).all():
            assert b.spent_epsilon == 1.0
