import pytest

from src.services import privacy


def test_sensitivity_replace_one_consultant():
    # 名单长度 n、裁剪宽度 w：替换一位顾问最多改变均值 w/n
    assert privacy.sensitivity_for(10, -20, 20) == pytest.approx(4.0)
    assert privacy.sensitivity_for(4, 0, 100) == pytest.approx(25.0)


def test_sensitivity_invalid():
    with pytest.raises(ValueError):
        privacy.sensitivity_for(0, -1, 1)
    with pytest.raises(ValueError):
        privacy.sensitivity_for(5, 10, 10)


def test_clipped_mean_bounds():
    diffs = [-50, -5, 0, 5, 50]
    mean, clipped, n = privacy.clipped_mean(diffs, -20, 20)
    assert clipped == [-20, -5, 0, 5, 20]
    assert n == 5
    assert mean == pytest.approx(0.0)


def test_deterministic_noise_reuses_same_value():
    n1 = privacy.deterministic_noise(request_id=7, epsilon=1.0, sensitivity=4.0)
    n2 = privacy.deterministic_noise(request_id=7, epsilon=1.0, sensitivity=4.0)
    assert n1 == n2  # 同申请同参数 -> 同噪声（重试复用）


def test_noise_differs_across_requests_and_params():
    base = privacy.deterministic_noise(1, 1.0, 4.0)
    other_id = privacy.deterministic_noise(2, 1.0, 4.0)
    other_eps = privacy.deterministic_noise(1, 2.0, 4.0)
    assert base != other_id
    assert base != other_eps


def test_laplace_noise_distribution_matches_scale():
    # 蒙特卡洛校验确定性反采样确实服从 Laplace(scale=b)：均值≈0、方差≈2b^2
    samples = []
    scale = 2.0
    for rid in range(1, 4001):
        samples.append(privacy.deterministic_noise(rid, epsilon=1.0,
                                                   sensitivity=scale * 1.0))
    mean = sum(samples) / len(samples)
    var = sum((x - mean) ** 2 for x in samples) / len(samples)
    assert abs(mean) < 0.2
    assert var == pytest.approx(2 * scale ** 2, rel=0.25)


def test_build_release_epsilon_delta_and_payload():
    diffs = [-10, 0, 10, 20]
    rel = privacy.build_release(diffs, -20, 20, epsilon=0.5, request_id=3)
    assert rel['n'] == 4
    assert rel['sensitivity'] == pytest.approx(10.0)   # 宽度40 / 4
    assert rel['noise_scale_b'] == pytest.approx(20.0)  # sensitivity / epsilon
    assert rel['delta'] == 0.0
    assert rel['noisy_mean'] == pytest.approx(rel['clipped_mean'] + rel['noise'])
    pub = privacy.public_payload(rel)
    # 对外产物不得包含内部均值、原始差值或顾问标识
    assert 'clipped_mean' not in pub
    assert 'noise' not in pub
    assert set(pub) == {
        'mechanism', 'adjacency', 'n', 'lower', 'upper', 'sensitivity',
        'epsilon', 'delta', 'noise_scale_b', 'noisy_mean',
    }
    assert pub['noisy_mean'] == rel['noisy_mean']


def test_replacing_one_consultant_bounded_by_sensitivity():
    # 直接验证相邻口径：替换名单中一位顾问，未加噪均值变化不超过敏感度
    lower, upper = -20, 20
    a = [-5, 2, 8, -3]
    b = [-5, 2, 8, 19]  # 仅最后一位被替换
    ma, _, _ = privacy.clipped_mean(a, lower, upper)
    mb, _, _ = privacy.clipped_mean(b, lower, upper)
    assert abs(mb - ma) <= privacy.sensitivity_for(4, lower, upper) + 1e-12
