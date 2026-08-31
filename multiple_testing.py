"""
Multiple-testing correction: Benjamini-Hochberg (FDR control).

Replaces the Bonferroni family-wise error rate correction. Where Bonferroni
asks "what's the chance of even one false positive across all tests?", BH
asks "what fraction of my declared discoveries do I expect to be false?" --
a less conservative target that adapts to the overall pattern of p-values
rather than penalizing every test equally regardless of how many genuinely
look significant.
"""


def benjamini_hochberg(p_values, fdr_level):
    """
    Standard BH step-up procedure.

    Given a list of p-values (one per test, any order) and a target FDR
    level Q (e.g. 0.05), finds the largest rank k (after sorting p-values
    ascending) such that p(k) <= (k / n) * Q, and marks every pair at rank
    1..k as passing.

    Returns:
        passes: list[bool], same order as the input p_values
        critical_pvalue: the largest p-value that still passed (the
            effective cutoff used), or None if nothing passed
    """
    n = len(p_values)
    if n == 0:
        return [], None

    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    max_rank_passing = 0
    for rank, (_, p) in enumerate(indexed, start=1):
        threshold = (rank / n) * fdr_level
        if p <= threshold:
            max_rank_passing = rank

    passes = [False] * n
    critical_pvalue = None
    if max_rank_passing > 0:
        critical_pvalue = indexed[max_rank_passing - 1][1]
        for rank in range(max_rank_passing):
            orig_idx, _ = indexed[rank]
            passes[orig_idx] = True

    return passes, critical_pvalue
