"""差分隐私匿名发布核心：裁剪均值、单顾问替换敏感度、拉普拉斯机制与确定性噪声。

设计要点：
- 发布量只有一个：固定名单内完整配对差值的裁剪均值，因此该顾问的全部 epsilon 都作用在这一个标量上。
- 敏感度按"替换一位顾问"（remove/adjacency 的 add/remove 等价口径）推导：
  名单长度为 n、裁剪区间宽度 w=upper-lower 时，替换一位顾问最多让裁剪均值改变 w/n。
- 拉普拉斯噪声尺度 b = sensitivity / epsilon，纯 epsilon-DP（delta=0）。
- 噪声由申请 ID 与机制参数经 SHA-256 反采样确定性生成：同一申请重试复用同一噪声，
  不依赖 numpy/random 的版本实现，跨环境、跨进程可复现，且不向外部暴露任何原始差值。
"""
import hashlib
import math

# 每位顾问跨组、跨评估、跨所有发布共享的累计隐私预算上限
TOTAL_EPSILON = 4.0
# 反采样时避开 0/1 端点，保证 log 有界且数值稳定
_UNIFORM_FLOOR = 1e-12
_UNIFORM_CEIL = 1.0 - 1e-12


def _uniform_stream(seed_material: bytes):
    """生成确定性的 [floor, ceil] 均匀分布流；每次产出 64 位随机量。"""
    counter = 0
    while True:
        digest = hashlib.sha256(seed_material + counter.to_bytes(8, 'big')).digest()
        word = int.from_bytes(digest[:8], 'big')
        u = _UNIFORM_FLOOR + (word / float(1 << 64)) * (_UNIFORM_CEIL - _UNIFORM_FLOOR)
        yield u
        counter += 1


def _laplace_inverse_cdf(u: float, scale: float) -> float:
    """拉普拉斯分布逆 CDF：u in (0,1) -> x，分布密度 (1/2b)exp(-|x|/b)。"""
    return -scale * math.log(1.0 - 2.0 * abs(u - 0.5)) * (1.0 if u >= 0.5 else -1.0)


def deterministic_noise(request_id: int, epsilon: float, sensitivity: float) -> float:
    """同一申请 ID + 同一机制参数永远得到同一噪声（重试复用，不重扣预算）。"""
    scale = sensitivity / epsilon
    seed = b'qingyin-laplace-v1:' + str(request_id).encode() + b':' + \
        repr(epsilon).encode() + b':' + repr(sensitivity).encode()
    u = next(_uniform_stream(seed))
    return _laplace_inverse_cdf(u, scale)


def clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def sensitivity_for(n: int, lower: float, upper: float) -> float:
    """替换一位顾问对裁剪均值的全局敏感度 = 裁剪宽度 / 名单长度。"""
    if n <= 0:
        raise ValueError('名单为空时不存在有限敏感度')
    if upper <= lower:
        raise ValueError('裁剪上界必须大于下界')
    return (upper - lower) / float(n)


def clipped_mean(differences, lower: float, upper: float):
    """对完整配对差值逐一裁剪到 [lower, upper] 后求均值，返回 (均值, 裁剪后差值, n)。"""
    clipped = [clip(float(d), lower, upper) for d in differences]
    if not clipped:
        raise ValueError('固定名单内没有完整配对样本，无法发布匿名均值')
    return sum(clipped) / len(clipped), clipped, len(clipped)


def build_release(differences, lower: float, upper: float, epsilon: float, request_id: int):
    """组装一次匿名发布的全部对外参数与加噪结果。

    对外只暴露：加噪均值、样本数、裁剪界、敏感度、epsilon、噪声尺度与机制说明，
    不包含任何顾问编号、原始得分或原始差值。
    """
    mean, clipped, n = clipped_mean(differences, lower, upper)
    sensitivity = sensitivity_for(n, lower, upper)
    if epsilon <= 0:
        raise ValueError('epsilon 必须为正数')
    scale = sensitivity / epsilon
    noise = deterministic_noise(request_id, epsilon, sensitivity)
    return {
        'n': n,
        'clipped_count': n,
        'lower': float(lower),
        'upper': float(upper),
        'clipped_mean': mean,                 # 内部留存，不进对外产物
        'sensitivity': sensitivity,
        'epsilon': float(epsilon),
        'delta': 0.0,
        'noise_scale_b': scale,
        'noise': noise,
        'noisy_mean': mean + noise,
        'mechanism': 'Laplace',
        'adjacency': 'replace-one-consultant',
    }


def public_payload(release: dict) -> dict:
    """剥离内部字段，仅保留允许对外分享的加噪均值与机制参数。"""
    return {
        'mechanism': release['mechanism'],
        'adjacency': release['adjacency'],
        'n': release['n'],
        'lower': release['lower'],
        'upper': release['upper'],
        'sensitivity': release['sensitivity'],
        'epsilon': release['epsilon'],
        'delta': release['delta'],
        'noise_scale_b': release['noise_scale_b'],
        'noisy_mean': release['noisy_mean'],
    }
