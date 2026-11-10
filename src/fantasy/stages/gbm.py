"""The gradient-boosted classifier shared by `availability` and `stat_line`."""

from sklearn.ensemble import HistGradientBoostingClassifier


def make_classifier(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=seed,
    )
