# Planning Documentation System - Usage Examples

## For Claude Code: Working with the Planning System

### Example 1: Starting a New Session
```
1. Read planning-docs/README.md (entry point)
2. Read SESSION_STATE.md (current task and progress)
3. Read DAILY_BACKLOG.md (today's priorities)
4. Check for latest session log in sessions/
```

### Example 2: Completing a Task
When you complete a task:
```
assistant: "I've finished implementing the OAuth2 authentication feature. Let me update the planning documentation."

<uses Task tool with subagent_type="project-manager">
prompt: "Update planning docs: OAuth2 authentication complete. Added endpoints, middleware, and tests. All tests passing."
```

### Example 3: Encountering a Blocker
When blocked:
```
assistant: "I'm blocked on the database migration - schema conflicts with existing user table. Let me document this."

<uses Task tool with subagent_type="project-manager">
prompt: "Blocker encountered: Database migration blocked by schema conflicts in user table. Need to resolve before continuing."
```

### Example 4: Making an Architectural Decision
When making technical decisions:
```
assistant: "I've decided to use Redis for caching instead of Memcached. Let me document this decision."

<uses Task tool with subagent_type="project-manager">
prompt: "Architectural decision: Using Redis for caching. Reasons: Better data structure support, persistence options, and existing integration."
```

## For Humans: Daily Workflow

### Morning Routine
1. Check `DAILY_BACKLOG.md` for today's priorities
2. Review `SESSION_STATE.md` for current context
3. Start working on highest priority task

### During Work
- SESSION_STATE.md auto-updates via project-manager
- Check progress periodically
- Review blockers if any appear

### End of Day
1. Review completed tasks in SESSION_STATE.md
2. Check tomorrow's priorities in DAILY_BACKLOG.md
3. Note any carried-over tasks

## Common Scenarios

### Scenario 1: Feature Implementation
```
Day 1: Planning and setup
- Read requirements in DAILY_BACKLOG
- Break down into subtasks
- Begin implementation

Day 2: Core development
- Continue from SESSION_STATE
- Complete main functionality
- Write tests

Day 3: Testing and polish
- Run full test suite
- Fix any issues
- Document completion
```

### Scenario 2: Bug Fix
```
1. Identify bug from DAILY_BACKLOG
2. Reproduce issue
3. Implement fix
4. Verify with tests
5. Trigger project-manager to update
```

### Scenario 3: Refactoring
```
1. Review scope in SPRINT_BACKLOG
2. Plan refactoring approach
3. Make incremental changes
4. Ensure tests pass at each step
5. Document improvements in DECISIONS.md
```

## Integration with KATO Development

### Test-Driven Development
```bash
# 1. Write test for new feature
vim tests/tests/unit/test_new_feature.py

# 2. Run test (should fail)
./kato-manager.sh test

# 3. Implement feature
vim kato/workers/new_feature.py

# 4. Run test again (should pass)
./kato-manager.sh test

# 5. Update planning docs
# Trigger project-manager to document completion
```

### Performance Optimization
```bash
# 1. Benchmark current performance
./run_benchmark.sh

# 2. Implement optimization
vim kato/searches/optimized_search.py

# 3. Benchmark again
./run_benchmark.sh

# 4. Compare results
# Document improvement in planning system
```

### Docker Development Workflow
```bash
# 1. Make code changes
vim kato/workers/kato_processor.py

# 2. Hot reload for testing
./update_container.sh

# 3. Run tests
./test-harness.sh test

# 4. If tests pass, rebuild
./kato-manager.sh build

# 5. Update planning docs
# Trigger project-manager
```

## Tips and Best Practices

### DO:
- ✅ Trigger project-manager after completing tasks
- ✅ Read SESSION_STATE.md at start of each session
- ✅ Document blockers immediately when encountered
- ✅ Update estimates based on actual time taken
- ✅ Archive completed work regularly

### DON'T:
- ❌ Edit planning-docs files directly (use project-manager)
- ❌ Skip documentation for "small" changes
- ❌ Leave tasks in "in_progress" indefinitely
- ❌ Ignore time estimates when planning
- ❌ Delete session logs (they're valuable history)

## Quick Reference Commands

```bash
# Check current status
cat planning-docs/SESSION_STATE.md | head -20

# View today's tasks
cat planning-docs/DAILY_BACKLOG.md

# Check weekly goals
cat planning-docs/SPRINT_BACKLOG.md

# Review recent decisions
cat planning-docs/DECISIONS.md

# Find completed features
ls planning-docs/completed/features/

# Check session history
ls -la planning-docs/sessions/
```

## Troubleshooting

### Issue: Planning docs out of sync
**Solution**: Trigger project-manager with current state

### Issue: Not sure what to work on
**Solution**: Check DAILY_BACKLOG.md, then SPRINT_BACKLOG.md

### Issue: Lost context from previous session
**Solution**: Read latest session log in sessions/

### Issue: Need to understand past decision
**Solution**: Check DECISIONS.md for rationale

### Issue: Task taking longer than expected
**Solution**: Update via project-manager, it will adjust estimates

---

*This guide provides practical examples for using the planning documentation system effectively with KATO development.*