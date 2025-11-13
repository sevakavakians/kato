# Git Workflow Guide

Git branching strategy and workflow for KATO development.

## Branching Strategy

KATO uses **Git Flow** with simplified conventions.

### Branch Types

#### main

- **Purpose**: Production-ready code
- **Protected**: Yes (requires PR + review)
- **Deploy**: Automatically to production
- **Lifetime**: Permanent

```bash
# Never commit directly to main
git checkout main  # ❌ Don't develop here
```

#### feature/*

- **Purpose**: New features or enhancements
- **Created from**: `main`
- **Merged to**: `main` (via PR)
- **Naming**: `feature/descriptive-name`
- **Lifetime**: Until merged

```bash
# Create feature branch
git checkout main
git pull origin main
git checkout -b feature/add-pattern-caching

# Work on feature
git add .
git commit -m "feat: add LRU cache for patterns"

# Push and create PR
git push origin feature/add-pattern-caching
```

#### bugfix/*

- **Purpose**: Bug fixes for issues in main
- **Created from**: `main`
- **Merged to**: `main` (via PR)
- **Naming**: `bugfix/issue-description`
- **Lifetime**: Until merged

```bash
# Create bugfix branch
git checkout main
git pull origin main
git checkout -b bugfix/fix-session-expiry

# Fix bug
git add .
git commit -m "fix: correct session TTL calculation"

# Push and create PR
git push origin bugfix/fix-session-expiry
```

#### hotfix/*

- **Purpose**: Critical production fixes
- **Created from**: `main`
- **Merged to**: `main` (expedited review)
- **Naming**: `hotfix/critical-issue`
- **Priority**: Highest

```bash
# Critical bug in production
git checkout main
git pull origin main
git checkout -b hotfix/memory-leak-in-processor

# Fix immediately
git add .
git commit -m "fix: resolve memory leak in pattern matching"

# Push and request expedited review
git push origin hotfix/memory-leak-in-processor
```

#### docs/*

- **Purpose**: Documentation-only changes
- **Created from**: `main`
- **Merged to**: `main` (via PR, lighter review)
- **Naming**: `docs/what-changed`

```bash
git checkout -b docs/update-api-reference
# Make documentation changes
git commit -m "docs: update API reference for v3.0"
```

#### refactor/*

- **Purpose**: Code refactoring without behavior changes
- **Created from**: `main`
- **Merged to**: `main` (via PR)
- **Naming**: `refactor/component-name`

```bash
git checkout -b refactor/simplify-pattern-search
# Refactor code
git commit -m "refactor: simplify pattern search logic"
```

## Commit Message Convention

### Format: Conventional Commits

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation only
- **style**: Code style changes (formatting, no logic change)
- **refactor**: Code refactoring
- **perf**: Performance improvement
- **test**: Adding or modifying tests
- **chore**: Build process, dependencies, tooling

### Examples

#### Feature

```
feat(api): add session configuration update endpoint

Implements PUT /sessions/{session_id}/config to allow updating
session configuration without creating a new session.

Closes #123
```

#### Bug Fix

```
fix(sessions): correct TTL auto-extend behavior

Session TTL was not properly resetting on each access when
SESSION_AUTO_EXTEND=true. Fixed by updating Redis EXPIRE
command after each successful operation.

Fixes #456
```

#### Documentation

```
docs(users): add troubleshooting guide

Created comprehensive troubleshooting guide covering common
issues with sessions, patterns, and predictions.
```

#### Refactor

```
refactor(workers): simplify pattern matching logic

Extracted match calculation into separate method for better
testability and reduced complexity.
```

### Commit Message Rules

1. **Subject line**:
   - Max 72 characters
   - Lowercase (except proper nouns)
   - Imperative mood ("add" not "added")
   - No period at end

2. **Body** (optional):
   - Wrap at 72 characters
   - Explain what and why, not how
   - Separate from subject with blank line

3. **Footer** (optional):
   - Reference issues: `Fixes #123`, `Closes #456`
   - Breaking changes: `BREAKING CHANGE: ...`
   - Co-authors: `Co-authored-by: Name <email>`

## Pull Request Workflow

### 1. Create Feature Branch

```bash
# Update main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/my-feature

# Make changes
# ...

# Commit changes
git add .
git commit -m "feat: implement my feature"
```

### 2. Push Branch

```bash
# Push to remote
git push origin feature/my-feature

# Or set upstream
git push -u origin feature/my-feature
```

### 3. Create Pull Request

**Via GitHub CLI**:
```bash
gh pr create --title "feat: implement my feature" \
  --body "$(cat <<'EOF'
## Summary
- Added new feature X
- Updated documentation
- Added tests

## Testing
- [x] Unit tests pass
- [x] Integration tests pass
- [x] Manual testing completed

## Related Issues
Closes #123

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Via GitHub Web UI**:
1. Navigate to repository
2. Click "Pull requests" → "New pull request"
3. Select `main` ← `feature/my-feature`
4. Fill in title and description
5. Click "Create pull request"

### 4. PR Template

```markdown
## Summary
Brief description of changes

## Changes
- Change 1
- Change 2
- Change 3

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed
- [ ] Documentation updated

## Related Issues
Fixes #123
Closes #456

## Screenshots (if applicable)
[Add screenshots]

## Checklist
- [ ] Code follows style guide
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] Breaking changes documented
```

### 5. Code Review

**Reviewer Checklist**:
- [ ] Code follows style guide
- [ ] Tests are comprehensive
- [ ] Documentation is clear
- [ ] No security vulnerabilities
- [ ] Performance is acceptable
- [ ] Error handling is appropriate

**Addressing Feedback**:
```bash
# Make requested changes
git add .
git commit -m "refactor: address review feedback"

# Push updates
git push origin feature/my-feature
```

### 6. Merge

**Merge Strategies**:

**Squash and Merge** (default):
- Combines all commits into one
- Use for feature branches
- Keeps main history clean

```bash
# GitHub UI: "Squash and merge"
# Or via CLI:
gh pr merge --squash
```

**Rebase and Merge**:
- Preserves individual commits
- Use for well-organized branches
- Linear history

```bash
gh pr merge --rebase
```

**Merge Commit**:
- Creates explicit merge commit
- Use for major features
- Preserves branch context

```bash
gh pr merge --merge
```

### 7. Cleanup

```bash
# After PR merged
git checkout main
git pull origin main

# Delete local branch
git branch -d feature/my-feature

# Delete remote branch (if not auto-deleted)
git push origin --delete feature/my-feature
```

## Common Workflows

### Sync with Main

Keep feature branch updated with main:

```bash
# Method 1: Rebase (cleaner history)
git checkout feature/my-feature
git fetch origin
git rebase origin/main

# Resolve conflicts if any
git add .
git rebase --continue

# Force push (rebase changes history)
git push origin feature/my-feature --force-with-lease
```

```bash
# Method 2: Merge (preserves history)
git checkout feature/my-feature
git fetch origin
git merge origin/main

# Resolve conflicts if any
git add .
git commit -m "merge: sync with main"

# Normal push
git push origin feature/my-feature
```

**Recommendation**: Use rebase for cleaner history, merge if commits are already pushed and reviewed.

### Amend Last Commit

```bash
# Make additional changes
git add .

# Amend last commit (don't add new commit)
git commit --amend --no-edit

# Or change commit message
git commit --amend -m "feat: updated commit message"

# Force push (rewrites history)
git push origin feature/my-feature --force-with-lease
```

**Warning**: Only amend commits that haven't been reviewed yet!

### Cherry-Pick Commits

```bash
# Apply specific commit from another branch
git checkout main
git cherry-pick abc123def456

# Or multiple commits
git cherry-pick abc123 def456 ghi789
```

### Stash Changes

```bash
# Save uncommitted changes
git stash save "work in progress"

# List stashes
git stash list

# Apply most recent stash
git stash pop

# Apply specific stash
git stash apply stash@{1}

# Delete stash
git stash drop stash@{0}
```

## Best Practices

### Branch Management

1. **Keep branches short-lived**: Merge within 1-2 weeks
2. **One feature per branch**: Easier to review and merge
3. **Update frequently**: Sync with main regularly
4. **Delete after merge**: Clean up merged branches
5. **Descriptive names**: `feature/add-redis-caching` not `feature/fix`

### Commit Practices

1. **Atomic commits**: One logical change per commit
2. **Meaningful messages**: Explain why, not what
3. **Test before commit**: Ensure tests pass
4. **Avoid "WIP" commits**: Squash before PR
5. **Signed commits**: Use GPG signing (optional)

```bash
# Sign commits
git commit -S -m "feat: add feature"

# Configure signing
git config --global user.signingkey YOUR_GPG_KEY
git config --global commit.gpgsign true
```

### Pull Request Practices

1. **Small PRs**: <400 lines changed ideal
2. **Clear description**: Context, changes, testing
3. **Link issues**: Reference related issues
4. **Request reviews**: Tag appropriate reviewers
5. **Respond promptly**: Address feedback quickly

### Conflict Resolution

```bash
# When conflicts occur during rebase/merge
git status  # See conflicting files

# Edit files to resolve conflicts
# Look for <<<<<<< HEAD markers

# After resolving
git add conflicted-file.py
git rebase --continue  # or git merge --continue

# If stuck, abort and try again
git rebase --abort  # or git merge --abort
```

## Git Hooks

### Pre-commit Hook

`.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Run linting before commit

echo "Running pre-commit checks..."

# Run ruff
ruff check kato/ tests/
if [ $? -ne 0 ]; then
    echo "❌ Ruff check failed"
    exit 1
fi

# Run black check
black --check kato/ tests/
if [ $? -ne 0 ]; then
    echo "❌ Black formatting check failed"
    echo "Run: black kato/ tests/"
    exit 1
fi

echo "✅ Pre-commit checks passed"
```

### Pre-push Hook

`.git/hooks/pre-push`:
```bash
#!/bin/bash
# Run tests before push

echo "Running tests before push..."

python -m pytest tests/ -v
if [ $? -ne 0 ]; then
    echo "❌ Tests failed"
    exit 1
fi

echo "✅ Tests passed"
```

## Troubleshooting

### Undo Last Commit (Keep Changes)

```bash
git reset --soft HEAD~1
```

### Undo Last Commit (Discard Changes)

```bash
git reset --hard HEAD~1
```

### Recover Deleted Branch

```bash
# Find commit SHA
git reflog

# Recreate branch
git checkout -b feature/my-feature abc123
```

### Clean Working Directory

```bash
# Remove untracked files (dry-run first)
git clean -n

# Actually remove
git clean -fd
```

## References

- **Git Flow**: https://nvie.com/posts/a-successful-git-branching-model/
- **Conventional Commits**: https://www.conventionalcommits.org/
- **GitHub Flow**: https://guides.github.com/introduction/flow/

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
