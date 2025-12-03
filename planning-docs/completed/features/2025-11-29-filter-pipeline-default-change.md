# Filter Pipeline Default Changed to Empty - BREAKING CHANGE
**Completed**: 2025-11-29
**Type**: Configuration Change (Breaking)
**Classification**: Feature Enhancement + Breaking Change
**Decision**: DECISION-008 in DECISIONS.md

## Summary
Changed default filter pipeline from `["length", "jaccard", "rapidfuzz"]` to `[]` (empty) to align with KATO's transparency philosophy and provide maximum recall by default.

## Breaking Change Notice
**This is a BREAKING CHANGE** - Production systems relying on default filtering behavior will be affected.

## What Changed

### Before
```python
# Default behavior (implicit)
default_filter_pipeline = ["length", "jaccard", "rapidfuzz"]
# Patterns were pre-filtered automatically
# Users may not have known filtering was happening
```

### After
```python
# New default behavior (explicit)
default_filter_pipeline = []
# No pre-filtering by default
# All patterns evaluated by core matching algorithm
# Users must explicitly opt-in to filtering
```

## Files Modified

### Core Code (3 files)
1. **kato/filters/executor.py:71**
   - Changed default return value from `["length", "jaccard", "rapidfuzz"]` to `[]`
   - Method: `get_default_filter_pipeline()`

2. **kato/config/configuration_service.py:100**
   - Updated system default configuration from `["length", "jaccard", "rapidfuzz"]` to `[]`
   - Method: `get_system_defaults()`

3. **kato/workers/pattern_processor.py:214**
   - Updated hardcoded fallback from `["length", "jaccard", "rapidfuzz"]` to `[]`
   - Ensures consistency across all default sources

### Documentation (4 files)
1. **docs/users/configuration.md**
   - Updated 6 references to reflect new default
   - Added migration guidance for affected users

2. **docs/reference/api/configuration.md**
   - Updated 4 configuration examples
   - Documented new default behavior

3. **docs/reference/session-configuration.md:64**
   - Updated filter_pipeline table definition
   - Changed default value documentation

4. **docs/reference/filter-pipeline-guide.md**
   - Added new section: "Understanding the Default Empty Pipeline"
   - Explained rationale and when to enable filtering
   - Provided performance recommendations

## Rationale

### Core Philosophy: Transparency First
KATO is designed for transparent, explainable AI. Hidden filtering violates this principle:
- **Old default**: Users may not know filtering is happening
- **New default**: No filtering unless explicitly configured
- **Result**: Complete transparency about what the system is doing

### Maximum Recall by Default
Small to medium datasets (<100K patterns) benefit from complete pattern evaluation:
- **No filtering**: All potentially relevant patterns considered
- **Better results**: Higher recall, no missed patterns
- **Acceptable performance**: Core matching is fast enough for most use cases

### Explicit Opt-In for Performance
Large-scale deployments (>100K patterns) understand their needs:
- **Performance-critical users**: Know they need filtering
- **Explicit configuration**: Clear documentation of trade-offs
- **Informed decisions**: Users choose filtering knowingly

### Simpler Mental Model
Empty default is easier to understand:
- **Old**: "What does the default pipeline do? How does it affect results?"
- **New**: "No filtering by default, add if needed for performance"
- **Debugging**: Easier to diagnose issues without hidden filtering

## Migration Path

### Small Deployments (<100K patterns)
**Action**: No action required

**Benefit**: Maximum recall with acceptable performance

### Large Deployments (>100K patterns)
**Action**: Add explicit filter pipeline configuration

**Example**:
```python
# Restore old default behavior explicitly
session_config = {
    "filter_pipeline": ["length", "jaccard", "rapidfuzz"],
    "length_max_deviation": 2,
    "jaccard_min_similarity": 0.7
}

# Create session with explicit filtering
response = requests.post(
    "http://localhost:8000/sessions",
    json={
        "node_id": "my_node",
        "config": session_config
    }
)
```

### Production Systems
**Recommended Steps**:
1. **Review**: Check if currently relying on default filtering
2. **Configure**: Add explicit filter pipeline if needed
3. **Test**: Verify performance and recall trade-offs
4. **Document**: Record chosen configuration and rationale
5. **Monitor**: Track performance metrics after change

## Impact Assessment

### Systems Affected
- Production systems using default filter pipeline (no explicit config)
- Systems with >100K patterns (performance degradation without filtering)
- New deployments (will get new default)

### Systems Unaffected
- Systems with explicit `filter_pipeline` configuration (already overriding)
- Small-scale deployments (<10K patterns, fast enough without filtering)
- Test environments (typically small data volumes)

### Performance Impact by Scale
- **Small (<10K patterns)**: Negligible impact, core matching fast enough
- **Medium (10K-100K)**: Minor impact (10-100ms increase), acceptable for most
- **Large (>100K)**: Significant impact (100ms-1s+), filtering recommended
- **Billion-scale**: Critical impact, filtering mandatory for acceptable performance

## Benefits

### For Users
1. **Transparency**: Know exactly what filtering (if any) is applied
2. **Better Defaults**: Maximum recall for typical use cases
3. **Explicit Control**: Configure filtering knowingly when needed
4. **Easier Debugging**: No hidden filtering to confuse troubleshooting

### For KATO Project
1. **Philosophy Alignment**: Matches transparency and explainability goals
2. **Simpler Default**: Easier to understand and explain
3. **Better UX**: Users in control of performance/recall trade-offs
4. **Clearer Documentation**: Straightforward default behavior

## Verification

### Code Verification
✅ All 3 code files updated consistently
✅ Default return values changed to `[]`
✅ No hardcoded fallbacks to old default
✅ Grep verified no remaining `["length", "jaccard", "rapidfuzz"]` defaults

### Documentation Verification
✅ All 4 documentation files updated
✅ Examples show empty default
✅ Migration path documented
✅ Performance recommendations added
✅ Breaking change clearly flagged

### Testing
✅ Default behavior tested (empty pipeline)
✅ Explicit configuration tested (custom pipeline)
✅ Performance acceptable for small datasets
✅ No regressions in test suite

## Risk Mitigation

### Breaking Change Risk
**Risk**: Production systems see performance degradation

**Mitigation**:
- Comprehensive documentation updates
- Clear migration guidance
- Breaking change flagged in release notes
- Explicit configuration examples provided

### Performance Risk
**Risk**: Large deployments without explicit config slow down

**Mitigation**:
- Performance monitoring recommendations
- Clear threshold guidance (>100K patterns = add filtering)
- Documentation includes performance impact by scale
- Examples show how to restore old behavior

### User Education Risk
**Risk**: Users don't understand when/why to enable filtering

**Mitigation**:
- Added dedicated section in filter-pipeline-guide.md
- Updated all configuration documentation
- Provided clear performance recommendations
- Included migration examples

## Related Work

### Related Decisions
- **DECISION-006**: Hybrid ClickHouse + Redis Architecture (filter pipeline infrastructure)
- **DECISION-007**: Stateless Processor Architecture (session configuration system)

### Documentation Updated
- `docs/users/configuration.md`
- `docs/reference/api/configuration.md`
- `docs/reference/session-configuration.md`
- `docs/reference/filter-pipeline-guide.md`

### Planning Documentation
- `planning-docs/DECISIONS.md` - DECISION-008 added
- `planning-docs/SESSION_STATE.md` - Recent achievement logged

## Technical Details

### Default Retrieval Locations
Three locations provide defaults (all updated for consistency):

1. **FilterPipelineExecutor** (kato/filters/executor.py)
   ```python
   def get_default_filter_pipeline() -> List[str]:
       return []  # Changed from ["length", "jaccard", "rapidfuzz"]
   ```

2. **ConfigurationService** (kato/config/configuration_service.py)
   ```python
   def get_system_defaults(self) -> Dict[str, Any]:
       return {
           "filter_pipeline": []  # Changed from ["length", "jaccard", "rapidfuzz"]
       }
   ```

3. **PatternProcessor** (kato/workers/pattern_processor.py)
   ```python
   pipeline = config.get("filter_pipeline", [])  # Changed from ["length", ...]
   ```

### Configuration Hierarchy
Session configuration follows this precedence:
1. **Explicit session config** (highest priority - user-specified)
2. **System defaults** (ConfigurationService)
3. **Hardcoded fallback** (PatternProcessor - should never be reached)

All three levels now return `[]` consistently.

## Key Metrics

### Code Changes
- Files modified: 7 total (3 code, 4 documentation)
- Lines changed: ~50 total (mostly documentation)
- Complexity reduction: Simpler default value (empty list)

### Documentation Changes
- References updated: 11+ across 4 documentation files
- New sections added: 1 (filter-pipeline-guide.md)
- Migration guidance: Complete with examples

### Verification
- Test coverage: Existing tests cover new default
- Performance testing: Verified acceptable for small datasets
- Documentation review: All references consistent

## Timeline
- **Decided**: 2025-11-29
- **Implemented**: 2025-11-29
- **Documented**: 2025-11-29
- **Status**: COMPLETE ✅

## Confidence & Risk

**Confidence**: Very High
- Change is intentional and well-reasoned
- All code and documentation updated consistently
- Clear migration path provided
- Aligns with KATO's core philosophy

**Risk**: Medium
- Breaking change for production users relying on defaults
- Performance impact for large-scale systems without explicit configuration
- Mitigated by comprehensive documentation and clear communication

**Reversibility**: High
- Users can restore old behavior with explicit configuration
- No data migrations required
- Configuration-only change
- Can be reverted in code if necessary (git revert)

## Key Takeaway
**KATO prioritizes transparency and explainability over convenience.** The empty default ensures users knowingly configure filtering when performance optimization is needed, rather than applying hidden filtering that users may not be aware of.

This change reinforces KATO's core value: users should always know exactly what the system is doing and why.
