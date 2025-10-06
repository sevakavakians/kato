"""
Sequence matching utilities for KATO.

Based on Python's difflib, provides helpers for computing deltas between sequences.
Simplified and optimized for KATO's pattern matching needs.

Classes:
    SequenceMatcher: Flexible class for comparing pairs of sequences.

Functions:
    _calculate_ratio: Calculate similarity ratio between sequences.
"""

from collections import namedtuple as _namedtuple
from collections.abc import Generator, Sequence
from functools import reduce
from typing import Any, Optional

__all__ = ['SequenceMatcher', 'Match']

Match = _namedtuple('Match', 'a b size')


def _calculate_ratio(matches: int, length: int) -> float:
    """Calculate the similarity ratio between sequences.

    Args:
        matches: Number of matching elements.
        length: Total length of both sequences.

    Returns:
        Ratio between 0.0 and 1.0, where 1.0 means identical sequences.
    """
    if length:
        return 2.0 * matches / length
    return 1.0


class SequenceMatcher:
    """Flexible class for comparing pairs of sequences of any type.

    The basic algorithm finds the longest contiguous matching subsequence
    that contains no "junk" elements. This is applied recursively to the
    pieces of the sequences to the left and right of the matching subsequence.

    This does not yield minimal edit sequences, but tends to yield matches
    that "look right" to people.

    Attributes:
        a: First sequence to compare.
        b: Second sequence to compare.
        b2j: Dict mapping elements in b to their indices.
        fullbcount: Dict with counts of elements in b.
        matching_blocks: List of matching block triples.
        opcodes: List of opcodes for transforming a into b.
    """

    def __init__(self, a: Sequence[Any] = '', b: Sequence[Any] = '') -> None:
        """Construct a SequenceMatcher.

        Args:
            a: First sequence to compare (elements must be hashable).
            b: Second sequence to compare (elements must be hashable).
        """
        self.a: Optional[Sequence[Any]] = None
        self.b: Optional[Sequence[Any]] = None
        self.b2j: dict[Any, list[int]] = {}
        self.fullbcount: Optional[dict[Any, int]] = None
        self.matching_blocks: Optional[list[tuple[int, int, int]]] = None
        self.opcodes: Optional[list[tuple[str, int, int, int, int]]] = None
        self.set_seqs(a, b)

    def set_seqs(self, a: Sequence[Any], b: Sequence[Any]) -> None:
        """Set the two sequences to be compared.

        Args:
            a: First sequence to compare.
            b: Second sequence to compare.

        Example:
            >>> s = SequenceMatcher()
            >>> s.set_seqs("abcd", "bcde")
            >>> s.ratio()
            0.75
        """
        self.set_seq1(a)
        self.set_seq2(b)

    def set_seq1(self, a: Sequence[Any]) -> None:
        """Set the first sequence to be compared.

        The second sequence to be compared is not changed.
        SequenceMatcher caches detailed information about the second sequence,
        so if comparing one sequence against many, use set_seq2() once
        and call set_seq1() repeatedly.

        Args:
            a: First sequence to compare.
        """
        if a is self.a:
            return
        self.a = a
        self.matching_blocks = self.opcodes = None

    def set_seq2(self, b: Sequence[Any]) -> None:
        """Set the second sequence to be compared.

        The first sequence to be compared is not changed.
        SequenceMatcher caches detailed information about the second sequence,
        so if comparing one sequence against many, use set_seq2() once
        and call set_seq1() repeatedly.

        Args:
            b: Second sequence to compare.
        """
        if b is self.b:
            return
        self.b = b
        self.matching_blocks = self.opcodes = None
        self.fullbcount = None
        self.__chain_b()

    def __chain_b(self) -> None:
        """Build b2j mapping for fast lookups.

        For each element x in b, set b2j[x] to a list of indices in b
        where x appears. The indices are in increasing order.
        """
        b = self.b
        self.b2j = b2j = {}

        for i, elt in enumerate(b):
            indices = b2j.setdefault(elt, [])
            indices.append(i)

    def find_longest_match(self, alo: int, ahi: int, blo: int, bhi: int) -> Match:
        """Find longest matching block in a[alo:ahi] and b[blo:bhi].

        Return (i,j,k) such that a[i:i+k] is equal to b[j:j+k], where
            alo <= i <= i+k <= ahi
            blo <= j <= j+k <= bhi
        and for all (i',j',k') meeting those conditions,
            k >= k'
            i <= i'
            and if i == i', j <= j'

        Args:
            alo: Start index in sequence a.
            ahi: End index in sequence a.
            blo: Start index in sequence b.
            bhi: End index in sequence b.

        Returns:
            Match namedtuple with (a, b, size) of the longest match.
            If no blocks match, returns (alo, blo, 0).

        Example:
            >>> s = SequenceMatcher(None, " abcd", "abcd abcd")
            >>> s.find_longest_match(0, 5, 0, 9)
            Match(a=0, b=4, size=5)
        """
        a, _, b2j = self.a, self.b, self.b2j
        besti, bestj, bestsize = alo, blo, 0

        # Find longest junk-free match
        j2len: dict[int, int] = {}
        nothing: list[int] = []

        for i in range(alo, ahi):
            j2lenget = j2len.get
            newj2len: dict[int, int] = {}

            for j in b2j.get(a[i], nothing):
                if j < blo:
                    continue
                if j >= bhi:
                    break
                k = newj2len[j] = j2lenget(j-1, 0) + 1
                if k > bestsize:
                    besti, bestj, bestsize = i-k+1, j-k+1, k
            j2len = newj2len

        return Match(besti, bestj, bestsize)

    def get_matching_blocks(self) -> list[Match]:
        """Return list of triples describing matching subsequences.

        Each triple is of the form (i, j, n), and means that
        a[i:i+n] == b[j:j+n]. The triples are monotonically increasing
        in i and j.

        The last triple is a dummy, (len(a), len(b), 0), and is the only
        triple with n==0.

        Returns:
            List of Match namedtuples describing matching blocks.

        Example:
            >>> s = SequenceMatcher(None, "abxcd", "abcd")
            >>> s.get_matching_blocks()
            [Match(a=0, b=0, size=2), Match(a=3, b=2, size=2), Match(a=5, b=4, size=0)]
        """
        if self.matching_blocks is not None:
            return list(map(Match._make, self.matching_blocks))

        la, lb = len(self.a), len(self.b)

        # Maintain a queue of blocks to examine
        queue: list[tuple[int, int, int, int]] = [(0, la, 0, lb)]
        matching_blocks: list[tuple[int, int, int]] = []

        while queue:
            alo, ahi, blo, bhi = queue.pop()
            i, j, k = x = self.find_longest_match(alo, ahi, blo, bhi)

            if k:  # If k is 0, there was no matching block
                matching_blocks.append(x)
                if alo < i and blo < j:
                    queue.append((alo, i, blo, j))
                if i+k < ahi and j+k < bhi:
                    queue.append((i+k, ahi, j+k, bhi))

        matching_blocks.sort()

        # Collapse adjacent equal blocks
        i1 = j1 = k1 = 0
        non_adjacent: list[tuple[int, int, int]] = []

        for i2, j2, k2 in matching_blocks:
            if i1 + k1 == i2 and j1 + k1 == j2:
                # Adjacent blocks - collapse them
                k1 += k2
            else:
                # Not adjacent
                if k1:
                    non_adjacent.append((i1, j1, k1))
                i1, j1, k1 = i2, j2, k2

        if k1:
            non_adjacent.append((i1, j1, k1))

        non_adjacent.append((la, lb, 0))
        self.matching_blocks = non_adjacent
        return list(map(Match._make, self.matching_blocks))

    def get_opcodes(self) -> list[tuple[str, int, int, int, int]]:
        """Return list of 5-tuples describing how to turn a into b.

        Each tuple is of the form (tag, i1, i2, j1, j2).
        The tags are:
            'replace': a[i1:i2] should be replaced by b[j1:j2]
            'delete': a[i1:i2] should be deleted
            'insert': b[j1:j2] should be inserted at a[i1:i1]
            'equal': a[i1:i2] == b[j1:j2]

        Returns:
            List of operation tuples.

        Example:
            >>> s = SequenceMatcher(None, "abcd", "bcde")
            >>> for tag, i1, i2, j1, j2 in s.get_opcodes():
            ...     print(f"{tag:7} a[{i1}:{i2}] b[{j1}:{j2}]")
            delete  a[0:1] b[0:0]
            equal   a[1:4] b[0:3]
            insert  a[4:4] b[3:4]
        """
        if self.opcodes is not None:
            return self.opcodes

        i = j = 0
        self.opcodes = answer = []

        for ai, bj, size in self.get_matching_blocks():
            tag = ''
            if i < ai and j < bj:
                tag = 'replace'
            elif i < ai:
                tag = 'delete'
            elif j < bj:
                tag = 'insert'

            if tag:
                answer.append((tag, i, ai, j, bj))

            i, j = ai+size, bj+size

            if size:
                answer.append(('equal', ai, i, bj, j))

        return answer

    def get_grouped_opcodes(self, n: int = 3) -> Generator[list[tuple[str, int, int, int, int]], None, None]:
        """Isolate change clusters by eliminating ranges with no changes.

        Return a generator of groups with up to n lines of context.
        Each group is in the same format as returned by get_opcodes().

        Args:
            n: Number of context lines to include.

        Yields:
            Groups of opcodes with context.
        """
        codes = self.get_opcodes()
        if not codes:
            codes = [("equal", 0, 1, 0, 1)]

        # Fixup leading and trailing groups if they show no changes
        if codes[0][0] == 'equal':
            tag, i1, i2, j1, j2 = codes[0]
            codes[0] = tag, max(i1, i2-n), i2, max(j1, j2-n), j2
        if codes[-1][0] == 'equal':
            tag, i1, i2, j1, j2 = codes[-1]
            codes[-1] = tag, i1, min(i2, i1+n), j1, min(j2, j1+n)

        nn = n + n
        group: list[tuple[str, int, int, int, int]] = []

        for tag, i1, i2, j1, j2 in codes:
            # End current group and start new one for large unchanged ranges
            if tag == 'equal' and i2-i1 > nn:
                group.append((tag, i1, min(i2, i1+n), j1, min(j2, j1+n)))
                yield group
                group = []
                i1, j1 = max(i1, i2-n), max(j1, j2-n)
            group.append((tag, i1, i2, j1, j2))

        if group and not (len(group)==1 and group[0][0] == 'equal'):
            yield group

    def ratio(self) -> float:
        """Return a measure of the sequences' similarity (float in [0,1]).

        Where T is the total number of elements in both sequences, and
        M is the number of matches, this is 2.0*M / T.

        Returns:
            1.0 if sequences are identical, 0.0 if they have nothing in common.

        Example:
            >>> s = SequenceMatcher(None, "abcd", "bcde")
            >>> s.ratio()
            0.75
        """
        matches = reduce(lambda sum, triple: sum + triple[-1],
                        self.get_matching_blocks(), 0)
        return _calculate_ratio(matches, len(self.a) + len(self.b))

    def quick_ratio(self) -> float:
        """Return an upper bound on ratio() relatively quickly.

        This is faster to compute than ratio() but only provides an upper bound.

        Returns:
            Upper bound on the similarity ratio.
        """
        if self.fullbcount is None:
            self.fullbcount = fullbcount = {}
            for elt in self.b:
                fullbcount[elt] = fullbcount.get(elt, 0) + 1
        fullbcount = self.fullbcount

        avail: dict[Any, int] = {}
        availhas, matches = avail.__contains__, 0

        for elt in self.a:
            numb = avail[elt] if availhas(elt) else fullbcount.get(elt, 0)
            avail[elt] = numb - 1
            if numb > 0:
                matches = matches + 1

        return _calculate_ratio(matches, len(self.a) + len(self.b))

    def real_quick_ratio(self) -> float:
        """Return an upper bound on ratio() very quickly.

        This is the fastest ratio computation but least accurate.

        Returns:
            Very rough upper bound on the similarity ratio.
        """
        la, lb = len(self.a), len(self.b)
        return _calculate_ratio(min(la, lb), la + lb)

    def compare(self) -> Generator[str, None, None]:
        """Compare two sequences; generate the resulting delta.

        Yields:
            Delta lines showing differences between sequences.
        """
        for tag, alo, ahi, blo, bhi in self.get_opcodes():
            if tag == 'replace':
                g = self._plain_replace(self.a, alo, ahi, self.b, blo, bhi)
            elif tag == 'delete':
                g = self._dump('-', self.a, alo, ahi)
            elif tag == 'insert':
                g = self._dump('+', self.b, blo, bhi)
            else:
                continue

            yield from g

    def _dump(self, tag: str, x: Sequence[Any], lo: int, hi: int) -> Generator[str, None, None]:
        """Generate comparison results for a same-tagged range.

        Args:
            tag: Tag character to prefix lines with.
            x: Sequence to dump.
            lo: Start index.
            hi: End index.

        Yields:
            Tagged lines from the sequence.
        """
        for i in range(lo, hi):
            yield '{} {}'.format(tag, x[i])

    def _plain_replace(self, a: Sequence[Any], alo: int, ahi: int,
                       b: Sequence[Any], blo: int, bhi: int) -> Generator[str, None, None]:
        """Generate replacement diff for two blocks.

        Args:
            a: First sequence.
            alo: Start index in a.
            ahi: End index in a.
            b: Second sequence.
            blo: Start index in b.
            bhi: End index in b.

        Yields:
            Diff lines showing the replacement.
        """
        assert alo < ahi and blo < bhi

        # Dump shorter block first to reduce memory burden
        if bhi - blo < ahi - alo:
            first = self._dump('+', b, blo, bhi)
            second = self._dump('-', a, alo, ahi)
        else:
            first = self._dump('-', a, alo, ahi)
            second = self._dump('+', b, blo, bhi)

        for g in first, second:
            yield from g
