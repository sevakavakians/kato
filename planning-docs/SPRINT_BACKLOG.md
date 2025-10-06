# SPRINT_BACKLOG.md - Upcoming Work
*Last Updated: 2025-10-06*

## Active Projects

### API Endpoint Deprecation - Session-Based Migration
**Priority**: Medium
**Status**: Phase 1 Complete

#### Phase 1: Deprecation Warnings ✅ COMPLETE
- [x] Add deprecation warnings to all direct endpoints
- [x] Update sample client with deprecation notices
- [x] Create comprehensive migration guide
- [x] Update test documentation
- **Completed**: 2025-10-06
- **Effort**: 1 hour

#### Phase 2: Auto-Session Middleware (NOT STARTED)
**Estimated Effort**: 3-4 hours
**Prerequisites**: Phase 1 committed and deployed

**Tasks**:
1. **Create Auto-Session Middleware** (1.5 hours)
   - File: `kato/middleware/auto_session.py`
   - Intercept direct endpoint requests
   - Extract processor_id from query params or X-Node-ID header
   - Check Redis for existing session mapping
   - Create session if needed with default config
   - Store `processor_id → session_id` mapping with TTL
   - Rewrite request path to session-based endpoint
   - Log auto-session creation warning

2. **Register Middleware** (0.5 hours)
   - File: `kato/services/kato_fastapi.py`
   - Import and register auto-session middleware
   - Add config flag: `ENABLE_AUTO_SESSION_MIDDLEWARE`
   - Ensure middleware runs before routing
   - Configure to only intercept deprecated endpoints

3. **Update Direct Endpoint Handlers** (0.5 hours)
   - File: `kato/api/endpoints/kato_ops.py`
   - Check for `X-Auto-Session-Created` header
   - Add tracking logs for middleware usage
   - Increment deprecation metrics

4. **Add Monitoring Metrics** (0.5 hours)
   - File: `kato/monitoring/metrics.py`
   - Metric: `deprecated_endpoint_calls_total`
   - Metric: `auto_session_created_total`
   - Add to `/metrics` endpoint

5. **Testing** (1 hour)
   - File: `tests/tests/middleware/test_auto_session.py`
   - Test auto-session creation per endpoint
   - Test processor_id → session_id mapping
   - Test TTL expiration and recreation
   - Test session-based endpoints unaffected
   - Test metrics increment correctly

6. **Documentation** (0.5 hours)
   - Update `docs/API_MIGRATION_GUIDE.md` Phase 2 section
   - Add middleware config to `CLAUDE.md`
   - Update README with backward compatibility notes

**Success Criteria**:
- Existing clients work without changes
- Automatic session creation is transparent
- Deprecation warnings still appear
- Metrics track deprecated endpoint usage
- All tests pass

#### Phase 3: Remove Direct Endpoints (NOT STARTED)
**Estimated Effort**: 2-3 hours
**Prerequisites**:
- Phase 2 deployed for 2-3 releases
- Metrics show <1% usage of deprecated endpoints
- User notification and migration complete

**Tasks**:
1. **Check Metrics Before Proceeding** (0.25 hours)
   - Review `deprecated_endpoint_calls_total` metrics
   - Document decision to proceed
   - Notify users if needed

2. **Remove Direct Endpoint Handlers** (0.5 hours)
   - File: `kato/api/endpoints/kato_ops.py`
   - Delete: `observe_primary`, `get_stm_primary`, `learn_primary`, etc.
   - Keep utility endpoints: `/genes/update`, `/gene/{name}`, `/pattern/{id}`
   - Remove router registrations

3. **Remove Auto-Session Middleware** (0.25 hours)
   - Delete: `kato/middleware/auto_session.py`
   - Remove from `kato/services/kato_fastapi.py`
   - Remove `ENABLE_AUTO_SESSION_MIDDLEWARE` config

4. **Update Processor Manager** (0.25 hours)
   - File: `kato/processors/processor_manager.py`
   - Remove `get_processor_by_id()` method
   - Keep only `get_processor()` with node_id

5. **Clean Up Client** (0.5 hours)
   - File: `sample-kato-client.py`
   - Remove all deprecated methods
   - Remove "Direct KATO Operations" section
   - Keep only session-based methods

6. **Update Tests** (0.5 hours)
   - Update `tests/tests/api/test_fastapi_endpoints.py`
   - Remove `tests/tests/middleware/test_auto_session.py`
   - Ensure all tests use session-based endpoints

7. **Documentation Cleanup** (0.5 hours)
   - Mark `docs/API_MIGRATION_GUIDE.md` as historical
   - Update `CLAUDE.md` - remove direct endpoint references
   - Create release notes

8. **Final Verification** (0.25 hours)
   - Run full test suite
   - Verify API docs at `/docs`
   - Test sample client examples
   - Smoke test common workflows

**Success Criteria**:
- No direct endpoints remain (except utilities)
- All tests pass with session-based endpoints
- API docs reflect session-only architecture
- Sample client shows only session methods
- Clean, single-path API

---

## Backlog (Future Work)

### Additional API Features
- Advanced session management endpoints
- Bulk pattern operations
- Pattern export/import functionality
- Enhanced metrics and monitoring

### Performance Optimizations
- Redis cache tuning
- Qdrant index optimization
- Response payload compression
- Connection pooling improvements

### Code Quality
- Continue technical debt monitoring
- Maintain >90% test coverage
- Monthly quality baseline reviews
- Pattern recognition for common issues

---

## Recently Completed

### Technical Debt Phase 5 (2025-10-06)
- 96% overall debt reduction (6,315 → 67 issues)
- 29 files improved
- Zero test regressions
- Foundation for future development

### Session Architecture Transformation (2025-09-26)
- Phase 1: Configuration centralization
- Phase 2: Multi-user session isolation
- Complete node_id-based routing

---

## Notes

**Development Philosophy**:
- Session-based endpoints are the future (Redis persistence + locking)
- Direct endpoints were interim solution (processor cache only)
- All future APIs should be session-based from the start

**Timeline Guidance**:
- Phase 2: Implement when ready for backward compatibility layer
- Phase 3: Only after monitoring metrics for 2-3 releases
- Don't rush Phase 3 - ensure smooth user migration
