import pytest
from fastapi.testclient import TestClient

from src.config.database import Base, Session, engine
from src.main import app
from src.models.entities import AnonRelease, User
from src.services import publish
from src.services.privacy import TOTAL_EPSILON
from src.utils.security import hash_password
from tests.factories import make_pair, make_evaluation, make_budgets, spend


@pytest.fixture()
def client(session):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as s:
        s.add(User(email='admin@demo.local', role='admin', password=hash_password('pw')))
        s.add(User(email='analyst@demo.local', role='analyst', password=hash_password('pw')))
        s.add(User(email='viewer@demo.local', role='viewer', password=hash_password('pw')))
        s.commit()

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides = {}
    from src.config.database import db
    app.dependency_overrides[db] = _db
    yield TestClient(app)
    app.dependency_overrides = {}


def _token(client, email):
    r = client.post('/auth/login', json={'email': email, 'password': 'pw'})
    return r.json()['token']


def _auth(token):
    return {'Authorization': 'Bearer ' + token}


def _seed_done_evaluation():
    with Session() as s:
        pairs = [make_pair(s, f'C{i}', before=70, after=73 + i) for i in range(5)]
        ev = make_evaluation(s, pairs=pairs)
        s.commit()
        codes = publish.fixed_roster(s, ev.id)[1]
        make_budgets(s, codes)
        s.commit()
        return ev.id, codes


def test_full_release_lifecycle_and_download_excludes_raw_data(client, artifact_dir):
    token = _token(client, 'analyst@demo.local')
    ev_id, codes = _seed_done_evaluation()

    # 创建发布
    r = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'name': '对外版', 'lower': -20, 'upper': 20, 'epsilon': 1.0,
    })
    assert r.status_code == 200, r.text
    rid = r.json()['id']
    assert r.json()['state'] == 'pending'
    assert r.json()['roster'] == codes  # 固定名单已冻结

    # 未完成前不能下载
    assert client.get(f'/releases/{rid}/download', headers=_auth(token)).status_code == 409

    # 执行 worker 处理
    with Session() as s:
        assert publish.process_release(s, rid) == 'downloadable'

    detail = client.get(f'/releases/{rid}', headers=_auth(token)).json()
    assert detail['state'] == 'downloadable'

    dl = client.get(f'/releases/{rid}/download', headers=_auth(token))
    assert dl.status_code == 200
    assert f'anon-release-{rid}.json' in dl.headers['content-disposition']
    payload = dl.json()
    assert set(payload) >= {'noisy_mean', 'sensitivity', 'epsilon', 'delta',
                            'noise_scale_b', 'mechanism', 'adjacency', 'n', 'lower', 'upper'}
    # 对外产物绝不含顾问编号、原始得分、内部未加噪均值
    text = dl.text
    for c in codes:
        assert c not in text
    assert 'clipped_mean' not in text and 'snapshot' not in text and 'pairs' not in text
    assert payload['mechanism'] == 'Laplace' and payload['delta'] == 0.0
    assert payload['sensitivity'] == 8.0  # 宽度40 / n5

    # 预算页面可见扣账与状态
    budget = client.get('/releases/budget', headers=_auth(token)).json()
    assert budget['total_epsilon_cap'] == TOTAL_EPSILON
    by_code = {a['consultant_code']: a for a in budget['accounts']}
    assert by_code[codes[0]]['spent_epsilon'] == pytest.approx(1.0)
    assert by_code[codes[0]]['remaining_epsilon'] == pytest.approx(TOTAL_EPSILON - 1.0)
    assert any(x['id'] == rid and x['state'] == 'downloadable' for x in budget['releases'])


def test_viewer_cannot_create_release(client):
    token = _token(client, 'viewer@demo.local')
    ev_id, _ = _seed_done_evaluation()
    r = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'lower': -20, 'upper': 20, 'epsilon': 1.0})
    assert r.status_code == 403
    # viewer 仍可只读查询预算
    assert client.get('/releases/budget', headers=_auth(token)).status_code == 200


def test_invalid_bounds_rejected(client):
    token = _token(client, 'analyst@demo.local')
    ev_id, _ = _seed_done_evaluation()
    r = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'lower': 20, 'upper': 20, 'epsilon': 1.0})
    assert r.status_code == 422


def test_release_on_unfinished_evaluation_rejected(client):
    token = _token(client, 'analyst@demo.local')
    with Session() as s:
        p = make_pair(s, 'C0')
        ev = make_evaluation(s, state='queued', pairs=[p])
        s.commit()
        ev_id = ev.id
    r = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'lower': -20, 'upper': 20, 'epsilon': 1.0})
    assert r.status_code == 409


def test_pre_check_rejects_when_budget_insufficient(client):
    token = _token(client, 'analyst@demo.local')
    ev_id, codes = _seed_done_evaluation()
    with Session() as s:
        spend(s, codes[0], TOTAL_EPSILON)  # 用尽一位顾问
        s.commit()
    r = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'lower': -20, 'upper': 20, 'epsilon': 1.0})
    assert r.status_code == 402
    # 预检拒绝不应创建申请
    with Session() as s:
        assert s.query(AnonRelease).count() == 0


def test_retry_endpoint_reuses_request(client, artifact_dir):
    token = _token(client, 'analyst@demo.local')
    ev_id, _ = _seed_done_evaluation()
    rid = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'lower': -20, 'upper': 20, 'epsilon': 1.0}).json()['id']
    with Session() as s:
        publish.process_release(s, rid)
    # 已可下载时重试被拒
    assert client.post(f'/releases/{rid}/retry', headers=_auth(token)).status_code == 409

    # 构造一个失败申请再重试
    rid2 = client.post('/releases', headers=_auth(token), json={
        'evaluation_id': ev_id, 'lower': -20, 'upper': 20, 'epsilon': 1.0}).json()['id']
    with Session() as s:
        row = s.get(AnonRelease, rid2)
        row.state = 'failed'
        row.error = '模拟失败'
        s.commit()
    rr = client.post(f'/releases/{rid2}/retry', headers=_auth(token))
    assert rr.status_code == 200 and rr.json()['state'] == 'pending'
    with Session() as s:
        assert publish.process_release(s, rid2) == 'downloadable'


def test_internal_report_still_available(client):
    # 内部原报告（含完整 pairs/snapshot）不受匿名发布影响
    token = _token(client, 'analyst@demo.local')
    ev_id, _ = _seed_done_evaluation()
    r = client.get(f'/evaluations/{ev_id}/export', headers=_auth(token))
    assert r.status_code == 200
    assert 'snapshot' in r.text
