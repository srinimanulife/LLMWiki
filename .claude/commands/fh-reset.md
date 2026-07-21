# /fh-reset — Reset Fusion Harness State

Clears any accumulated context that could cause stale role confusion or
Anthropic classifier false-positives on long sessions.

## Instructions for Claude

When this command is invoked:

1. Acknowledge the reset:
```
## 🔄 Fusion Harness Reset

Clearing fusion harness state:
- Architect role memory: cleared ✅
- Builder session context: cleared ✅  
- Validation round counter: reset to 0 ✅
```

2. Remind the user of available commands:
```
### Available Fusion Commands
| Command | Purpose |
|---------|---------|
| `/opinion <prompt>` | Side-by-side Claude vs Codex comparison |
| `/fusion "<prompt>" "<merge instruction>"` | Parallel workers + merge agent |
| `/auto-validate <task>` | Build-and-gate loop (Validator → Builder → Gate) |
| `/fh-reset` | This command — reset state |

### Current Config
- Architect: Claude (this session)
- Builder: gpt-5.3-codex-2 via Azure proxy at http://127.0.0.1:18080
- Proxy status: check with `curl -s http://127.0.0.1:18080/health`
```

3. You are now in a fresh fusion harness state. Await the next command.
