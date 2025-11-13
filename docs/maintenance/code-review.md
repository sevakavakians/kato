# KATO Code Review Guidelines

## Overview

Effective code reviews ensure code quality, knowledge sharing, and maintainability. This guide covers review process, checklist, and best practices.

## Table of Contents
1. [Review Process](#review-process)
2. [Review Checklist](#review-checklist)
3. [Providing Feedback](#providing-feedback)
4. [Review Standards](#review-standards)
5. [Common Issues](#common-issues)

## Review Process

### Pull Request Workflow

```
1. Create PR → 2. CI Checks → 3. Code Review → 4. Address Feedback → 5. Merge
```

### Roles

**Author Responsibilities:**
- Write clear PR description
- Self-review before requesting review
- Respond to feedback promptly
- Update based on suggestions
- Ensure CI passes

**Reviewer Responsibilities:**
- Review within 24 hours
- Provide constructive feedback
- Test changes locally if needed
- Approve when satisfied
- Share knowledge

## Review Checklist

### Functionality

- [ ] Code does what PR claims
- [ ] Edge cases handled
- [ ] Error handling appropriate
- [ ] No obvious bugs
- [ ] Performance acceptable

### Code Quality

- [ ] Follows style guide
- [ ] No code duplication
- [ ] Functions are small and focused
- [ ] Variable names clear
- [ ] Complexity reasonable (<10)

### Testing

- [ ] Tests included for new code
- [ ] Tests cover edge cases
- [ ] All tests pass
- [ ] Coverage maintained or improved

### Documentation

- [ ] Public APIs documented
- [ ] Complex logic explained
- [ ] CHANGELOG.md updated
- [ ] README.md updated if needed

### Security

- [ ] No secrets in code
- [ ] Input validation present
- [ ] SQL injection prevented
- [ ] Dependencies secure

## Providing Feedback

### Feedback Categories

Use conventional comment prefixes:

- **[blocking]** - Must fix before merge
- **[suggestion]** - Nice to have, not required
- **[question]** - Seeking clarification
- **[nitpick]** - Minor style issue
- **[praise]** - Positive feedback

### Examples

✅ **Good Feedback:**
```
[blocking] This function doesn't handle the case where `session_id` is None.
Consider adding validation at the beginning:

    if session_id is None:
        raise ValueError("session_id cannot be None")

[suggestion] We could simplify this loop using a list comprehension:

    results = [process(item) for item in items if item.is_valid()]

[question] What happens when `patterns` is empty? Should we return an empty
list or raise an exception?

[praise] Nice refactoring! This is much clearer than the previous version.
```

❌ **Bad Feedback:**
```
This is wrong.
Fix this.
I don't like this approach.
```

### Tone Guidelines

- Be respectful and constructive
- Focus on code, not person
- Ask questions, don't command
- Explain reasoning
- Provide examples
- Give praise for good code

## Review Standards

### Small PRs

**Target:** <400 lines changed

Benefits:
- Faster reviews
- Better feedback
- Fewer bugs
- Easier rollback

```bash
# Check PR size
git diff main --stat
```

### Response Time

- **First response:** <24 hours
- **Follow-up:** <4 hours during work hours
- **Final approval:** <48 hours total

### Approval Requirements

- **1 approval minimum**
- **All CI checks pass**
- **No unresolved conversations**
- **Author approval for changes**

## Common Issues

### Issue: Missing Tests

```
[blocking] This new function needs tests. Please add:
1. Test for happy path
2. Test for error case when input is invalid
3. Test for edge case with empty list
```

### Issue: Poor Error Handling

❌ **Before:**
```python
def get_session(session_id):
    return sessions[session_id]  # KeyError if not found
```

✅ **After:**
```python
def get_session(session_id: str) -> Session:
    if session_id not in sessions:
        raise SessionNotFoundError(f"Session {session_id} not found")
    return sessions[session_id]
```

### Issue: Code Duplication

```
[blocking] This logic is duplicated in three places. Let's extract it:

def validate_observation(obs: dict) -> None:
    if not obs.get("strings"):
        raise ValueError("strings required")
    if not isinstance(obs["vectors"], list):
        raise TypeError("vectors must be list")
```

### Issue: Missing Documentation

```
[blocking] Please add docstring explaining:
- What this function does
- Parameter descriptions
- Return value meaning
- Example usage
```

### Issue: Performance Concern

```
[question] This loops through all patterns on every request.
Have we tested performance with 10k+ patterns?

[suggestion] Consider adding caching or indexing here.
```

## Best Practices

### For Authors

1. **Self-review first** - Catch obvious issues
2. **Small PRs** - <400 lines when possible
3. **Clear description** - Explain what and why
4. **Screenshots** - For UI changes
5. **Test locally** - Verify all tests pass
6. **Link issues** - Reference related issues
7. **Update docs** - Keep documentation current

### For Reviewers

1. **Review promptly** - <24 hours
2. **Be constructive** - Explain reasoning
3. **Test locally** - For complex changes
4. **Check tests** - Verify coverage
5. **Ask questions** - Seek understanding
6. **Give praise** - Recognize good work
7. **Use labels** - [blocking], [suggestion], etc.

## PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (patch)
- [ ] New feature (minor)
- [ ] Breaking change (major)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guide
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Tests pass locally
- [ ] No merge conflicts

## Related Issues
Closes #123
```

## Related Documentation

- [Code Quality Standards](code-quality.md)
- [Testing Standards](testing-standards.md)
- [Contributing Guide](/docs/developers/contributing.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
