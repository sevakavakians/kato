# KATO Technical Debt Management

## Overview

Process for identifying, tracking, prioritizing, and remediating technical debt in KATO.

## Table of Contents
1. [Debt Identification](#debt-identification)
2. [Debt Categories](#debt-categories)
3. [Tracking System](#tracking-system)
4. [Prioritization](#prioritization)
5. [Remediation Strategy](#remediation-strategy)

## Debt Identification

### Sources of Technical Debt

1. **Intentional Shortcuts** - Deliberate trade-offs for speed
2. **Outdated Patterns** - Code predating better practices
3. **Incomplete Refactoring** - Partial migrations
4. **Missing Tests** - Untested or under-tested code
5. **Documentation Gaps** - Undocumented functionality
6. **Performance Issues** - Known inefficiencies
7. **Deprecated Dependencies** - Old library versions

### Identifying Debt

```python
# Code markers
# TODO: Refactor this into smaller functions (complexity: 15)
# FIXME: Memory leak when processing large datasets
# HACK: Workaround for bug in library X
# DEBT: Should use async/await pattern here
# PERF: O(n²) algorithm, can be optimized to O(n log n)
```

```bash
# Find debt markers
grep -r "TODO\|FIXME\|HACK\|DEBT\|PERF" kato/

# Check complexity
radon cc kato/ -n C  # Functions with complexity >10

# Find missing tests
pytest --cov=kato --cov-report=term-missing tests/
```

## Debt Categories

### Category 1: Code Quality Debt

**Examples:**
- High cyclomatic complexity (>10)
- Code duplication
- Long functions (>100 lines)
- Poor naming

**Impact:** Maintainability, readability

```python
# Example debt
def process_data(data):  # DEBT: Split into smaller functions
    # ... 200 lines of code ...
    pass

# Remediation
def process_data(data):
    validated = validate_data(data)
    transformed = transform_data(validated)
    return persist_data(transformed)
```

### Category 2: Architecture Debt

**Examples:**
- Tight coupling between modules
- Missing abstractions
- Inconsistent patterns
- Monolithic components

**Impact:** Scalability, testability

```python
# Example debt
class KatoProcessor:
    def __init__(self):
        self.db = MongoClient()  # DEBT: Tight coupling
        self.cache = Redis()
```

### Category 3: Test Debt

**Examples:**
- Missing tests (<80% coverage)
- Flaky tests
- Slow tests
- No integration tests

**Impact:** Reliability, confidence in changes

### Category 4: Documentation Debt

**Examples:**
- Missing docstrings
- Outdated documentation
- No examples
- Unclear API docs

**Impact:** Developer productivity, onboarding

### Category 5: Performance Debt

**Examples:**
- N+1 queries
- Memory leaks
- Inefficient algorithms
- No caching

**Impact:** User experience, cost

## Tracking System

### GitHub Issues

```markdown
**Title:** [DEBT] Reduce pattern_processor.py complexity

**Labels:** technical-debt, code-quality, priority-medium

**Description:**
The `process_pattern()` function has cyclomatic complexity of 18.
Should be refactored to <10.

**Current State:**
- File: kato/workers/pattern_processor.py
- Function: process_pattern()
- Complexity: 18
- Lines: 156

**Proposed Solution:**
Extract helper functions:
- validate_pattern()
- apply_filters()
- match_candidates()
- rank_results()

**Impact:**
- Maintainability: High
- Performance: None
- Risk: Low

**Effort:** ~4 hours

**References:**
- Complexity report: [link]
- Related issue: #123
```

### Debt Register

```yaml
# .github/DEBT_REGISTER.yaml
technical_debt:
  - id: DEBT-001
    category: code-quality
    severity: medium
    component: pattern_processor
    description: High cyclomatic complexity in process_pattern()
    current_value: 18
    target_value: 10
    created: 2025-10-15
    estimated_effort: 4h
    priority: 3

  - id: DEBT-002
    category: performance
    severity: high
    component: database_queries
    description: N+1 query problem in get_patterns()
    impact: 500ms latency per request
    created: 2025-09-20
    estimated_effort: 8h
    priority: 1
```

## Prioritization

### Debt Scoring

```python
def calculate_debt_score(debt: TechnicalDebt) -> float:
    """Calculate debt priority score."""
    # Impact: 1-10 (higher = worse)
    impact = debt.impact_score

    # Effort: hours to fix
    effort = debt.estimated_effort_hours

    # Age: months since identified
    age = debt.age_months

    # Cost of delay: impact * age
    cost_of_delay = impact * age

    # Priority: maximize (cost of delay / effort)
    return cost_of_delay / effort

# Example
debt = TechnicalDebt(
    impact_score=8,  # High impact
    estimated_effort_hours=4,
    age_months=3
)
score = calculate_debt_score(debt)
# score = (8 * 3) / 4 = 6.0
```

### Prioritization Matrix

| Priority | Impact | Effort | Action |
|----------|--------|--------|--------|
| P0 | Critical | Any | Fix immediately |
| P1 | High | Low | Fix this sprint |
| P2 | High | High | Schedule next quarter |
| P3 | Medium | Low | Fix when convenient |
| P4 | Low | High | Document, maybe never fix |

## Remediation Strategy

### Sprint Allocation

**20% Rule:** Dedicate 20% of each sprint to debt remediation.

```
Sprint Capacity: 40 hours
  - New features: 32 hours (80%)
  - Tech debt: 8 hours (20%)
```

### Debt Days

**Monthly Debt Day:** One day per month focused entirely on debt.

### Incremental Refactoring

**Boy Scout Rule:** Leave code better than you found it.

```python
# Before (found in codebase)
def process(data):
    # 50 lines of complex code
    pass

# After (incremental improvement)
def process(data):
    """Process data and return results.

    Args:
        data: Input data dictionary

    Returns:
        Processed results
    """
    validated = _validate_input(data)  # Extracted
    return _process_validated(validated)  # Extracted

def _validate_input(data):
    """Validate input data."""
    # Validation logic extracted for clarity
    pass

def _process_validated(data):
    """Process validated data."""
    # Processing logic
    pass
```

### Debt Spikes

**Time-boxed investigation** for large debt items.

```markdown
**Debt Spike: Migrate to Async Pattern**

**Goal:** Investigate effort to migrate synchronous code to async/await

**Time Box:** 4 hours

**Deliverables:**
1. Analysis of current blocking calls
2. List of functions requiring changes
3. Estimated effort for full migration
4. Proof of concept for critical path

**Outcome:**
- 47 functions need changes
- Estimated: 40 hours
- Recommendation: Incremental migration starting with API layer
```

## Tracking Metrics

### Debt Metrics Dashboard

```python
class DebtMetrics:
    """Track technical debt metrics."""

    @property
    def total_debt_items(self) -> int:
        """Count of open debt items."""
        return len(self.debt_register)

    @property
    def debt_by_severity(self) -> dict:
        """Debt grouped by severity."""
        return {
            "critical": [d for d in self.debt_register if d.severity == "critical"],
            "high": [d for d in self.debt_register if d.severity == "high"],
            "medium": [d for d in self.debt_register if d.severity == "medium"],
            "low": [d for d in self.debt_register if d.severity == "low"],
        }

    @property
    def average_debt_age(self) -> float:
        """Average age of debt items in months."""
        return sum(d.age_months for d in self.debt_register) / len(self.debt_register)

    @property
    def debt_remediation_rate(self) -> float:
        """Items closed per month."""
        # Calculate from history
        pass
```

## Preventing New Debt

### Code Review Checklist

- [ ] No `TODO` markers without issue reference
- [ ] Complexity <10 for all functions
- [ ] Test coverage maintained
- [ ] Documentation complete
- [ ] No obvious performance issues

### CI/CD Gates

```yaml
# Fail build if debt increases
- name: Check complexity
  run: |
    radon cc kato/ -n C --total-average
    # Fail if average complexity increases

- name: Check coverage
  run: |
    pytest --cov=kato --cov-fail-under=80 tests/
```

### Architecture Decision Records (ADRs)

Document intentional technical decisions:

```markdown
# ADR-015: Use synchronous database calls (temporary)

**Status:** Accepted (temporary)

**Context:** Async migration would take 40 hours

**Decision:** Use synchronous calls, document as tech debt

**Consequences:**
- Lower throughput (acceptable for current scale)
- Technical debt: DEBT-025
- Must migrate before 10k RPS

**Debt Remediation:**
- Priority: P2 (high impact, high effort)
- Target: Q2 2025
```

## Best Practices

1. **Measure regularly** - Track debt metrics
2. **Allocate time** - 20% of sprints
3. **Prioritize ruthlessly** - Fix high-impact, low-effort first
4. **Prevent new debt** - Code review standards
5. **Document decisions** - Use ADRs
6. **Incremental improvement** - Boy Scout Rule
7. **Regular review** - Monthly debt review meeting

## Related Documentation

- [Code Quality Standards](code-quality.md)
- [Code Review Guidelines](code-review.md)
- [Contributing Guide](/docs/developers/contributing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
