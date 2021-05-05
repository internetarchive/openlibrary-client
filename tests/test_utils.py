import pytest
from olclient.utils import merge_unique_lists


merge_cases = [
    ([[1, 2], [2, 3]], [1, 2, 3]),
    ([[1, 2, 2, 2], [2, 2, 3]], [1, 2, 3]),
    ([[9, 10]], [9, 10]),
    ([[1, 1, 1, 1]], [1]),
    ([], []),
    ([[2], [1]], [2, 1]),
]


@pytest.mark.parametrize("input_,merged", merge_cases)
def test_merge_unique_lists(input_, merged):
    assert merge_unique_lists(input_) == merged
