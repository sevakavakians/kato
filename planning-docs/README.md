# Planning Documentation System - Quick Start Guide

## Purpose
This planning system ensures development continuity across sessions and provides intelligent context management for the KATO project.

## For Claude Code: Context Loading Strategy

### 1. ALWAYS Start Here (Immediate Context)
Read these files in order:
1. **This file** (`planning-docs/README.md`) - You are here
2. **SESSION_STATE.md** - Current task and progress
3. **DAILY_BACKLOG.md** - Today's priorities
4. **Latest session log** in `sessions/` folder (if exists)

### 2. Load When Needed (On-Demand Context)
Only read these when relevant to current task:
- **PROJECT_OVERVIEW.md** - When needing project scope/tech info
- **ARCHITECTURE.md** - When making structural decisions
- **SPRINT_BACKLOG.md** - When planning beyond today
- **DECISIONS.md** - When questioning past choices
- **Historical sessions/** - When investigating past work
- **completed/** - When building on previous features

### 3. Current System Status

**Active Development**: Planning Documentation System Implementation
**Last Updated**: 2025-08-29
**Session Focus**: Creating planning infrastructure

**Quick Status Check**:
```bash
# View current git status
git status

# Check KATO system status
./kato-manager.sh status

# Run tests
./test-harness.sh test
```

## Document Purposes (Quick Reference)

| Document | Purpose | Update Frequency |
|----------|---------|------------------|
| SESSION_STATE.md | Live development status | Every 30 minutes |
| PROJECT_OVERVIEW.md | Master project reference | Weekly |
| DAILY_BACKLOG.md | Today's tasks | Morning & Evening |
| SPRINT_BACKLOG.md | Week's planned work | Weekly |
| ARCHITECTURE.md | Technical documentation | As needed |
| DECISIONS.md | Decision log | When decisions made |

## Automated Maintenance

The **project-manager** agent automatically updates documentation when:
- Tasks are completed
- New tasks are added
- Blockers are identified
- Architectural decisions are made
- Context switches occur

## Quick Commands for KATO Development

```bash
# Start development environment
./kato-manager.sh start

# Run tests in container
./test-harness.sh test

# Hot reload changes
./update_container.sh

# View logs
docker logs kato-primary --tail 20

# Check API health
curl http://localhost:8001/health
```

## Folder Structure
```
planning-docs/
├── README.md              # You are here
├── SESSION_STATE.md       # Current task status
├── PROJECT_OVERVIEW.md    # Project reference
├── DAILY_BACKLOG.md      # Today's tasks
├── SPRINT_BACKLOG.md     # Week's tasks
├── ARCHITECTURE.md       # Technical docs
├── DECISIONS.md          # Decision log
├── sessions/             # Session logs
├── completed/            # Archived work
└── project-manager/  # Agent workspace
```

## For Humans: Using This System

1. **Start of Day**: Check DAILY_BACKLOG.md
2. **During Work**: SESSION_STATE.md auto-updates
3. **Making Decisions**: Add to DECISIONS.md
4. **End of Day**: Review progress in SESSION_STATE.md
5. **Weekly Planning**: Update SPRINT_BACKLOG.md

## For Claude Code: Your Protocol

1. **Every Session Start**: Read this README → SESSION_STATE → DAILY_BACKLOG
2. **During Work**: Update SESSION_STATE.md every 30 minutes
3. **Task Completion**: Trigger project-manager
4. **Context Switch**: Archive current work, update state
5. **Decision Made**: Log in DECISIONS.md with rationale

## Integration with KATO Workflow

This planning system integrates with:
- **kato-manager.sh**: Development commands
- **test-harness.sh**: Testing workflow
- **update_container.sh**: Hot reload during development
- **Docker ecosystem**: Container-based development

## Current Focus Areas

Based on SESSION_STATE.md:
- Implementing planning documentation system
- Test suite stabilization
- Documentation updates

## Need Help?

- Check PROJECT_OVERVIEW.md for project details
- Review ARCHITECTURE.md for technical decisions
- See DECISIONS.md for historical context
- Examine completed/ for similar past work

---

*This README is the entry point for all planning documentation. Start here, load what you need, ignore what you don't.*