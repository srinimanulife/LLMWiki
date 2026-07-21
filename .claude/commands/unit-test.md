# /unit-test — Codex Unit Test Generator + Fix Loop

Generate unit tests for any file or function using Codex (Azure proxy),
run them, and loop on failures until green or max rounds reached.

## Usage
```
/unit-test <file_path> [framework] [extra_instructions]
```

**Examples:**
```
/unit-test code/lambda/query/handler.py
/unit-test code/lambda/query/handler.py pytest "mock all boto3 calls"
/unit-test src/utils/parser.js jest
/unit-test code/neuro_san/coded_tools/llmwiki/llmwiki_base_tool.py pytest "cover all public methods"
```

**Arguments:**
- `file_path` — required. Path to the file to test (relative to cwd or absolute).
- `framework` — optional. `pytest` (default for .py), `jest` (default for .js/.ts), `unittest`, `mocha`.
- `extra_instructions` — optional quoted string. Any extra constraints for Codex.

---

## Instructions for Claude

When invoked with `$ARGUMENTS`:

### Step 0 — Parse arguments
Parse `$ARGUMENTS`:
- First token = FILE_PATH
- Second token (if no spaces / not quoted) = FRAMEWORK
- Quoted string = EXTRA_INSTRUCTIONS

Auto-detect FRAMEWORK from extension if not provided:
- `.py` → `pytest`
- `.js` / `.ts` / `.tsx` → `jest`
- `.java` → `junit`
- `.go` → `go test`

Read FILE_PATH using the Read tool. Extract:
- Language
- All public functions / methods / classes
- Any existing imports or dependencies

Display:
```
## 📂 Target File — <FILE_PATH>
**Language:** <language>
**Framework:** <FRAMEWORK>
**Symbols to test:** <comma-separated list of functions/classes>
```

---

### Phase 1 — Codex generates tests

POST to `http://127.0.0.1:18080/openai/responses`:
```json
{
  "model": "gpt-5.3-codex-2",
  "input": "You are a senior test engineer.\n\nWrite comprehensive unit tests for the following <LANGUAGE> file using <FRAMEWORK>.\n\nRequirements:\n- Test every public function and method\n- Include: happy path, edge cases, error/exception handling\n- Mock all external calls (HTTP, DB, AWS SDK, filesystem) with appropriate mocking libraries\n- Each test must have a descriptive name explaining what it verifies\n- Tests must be runnable standalone with no manual setup\n<EXTRA_INSTRUCTIONS>\n\nSource file (<FILE_PATH>):\n<FILE_CONTENTS>\n\nReturn ONLY the complete test file. No explanation.",
  "reasoning": { "effort": "high" }
}
```
Header: `Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e`

Determine the test file path:
- For `path/to/foo.py` → `path/to/test_foo.py`
- For `src/bar.js` → `src/bar.test.js`
- For `src/baz.ts` → `src/baz.test.ts`

Write the generated test file to TEST_FILE_PATH using the Write tool.

Display:
```
## ⚡ Codex — Generated Tests (Round 1)
**Written to:** <TEST_FILE_PATH>
\`\`\`<language>
<test file contents>
\`\`\`
```

---

### Phase 2 — Run the tests

Run the appropriate command via Bash:

| Framework | Command |
|-----------|---------|
| pytest    | `python -m pytest <TEST_FILE_PATH> -v 2>&1` |
| unittest  | `python -m unittest <TEST_FILE_PATH> -v 2>&1` |
| jest      | `npx jest <TEST_FILE_PATH> --no-coverage 2>&1` |
| mocha     | `npx mocha <TEST_FILE_PATH> 2>&1` |
| go test   | `go test ./... -v 2>&1` |
| junit     | `mvn test 2>&1` |

Capture full output as TEST_OUTPUT.

Display:
```
## 🚦 Test Run — Round N
\`\`\`
<TEST_OUTPUT>
\`\`\`
**Status:** PASS ✅ / FAIL ❌ (<N passed> / <M failed>)
```

---

### Phase 3 — Loop on failure

**If PASS** → go to Phase 4.

**If FAIL and rounds < 3:**

POST to `http://127.0.0.1:18080/openai/responses`:
```json
{
  "model": "gpt-5.3-codex-2",
  "input": "The unit tests you generated have failures. Fix them.\n\nSource file (<FILE_PATH>):\n<FILE_CONTENTS>\n\nCurrent test file:\n<CURRENT_TEST_CONTENTS>\n\nTest runner output:\n<TEST_OUTPUT>\n\nFix ONLY what is failing. Do not remove passing tests. Return the complete corrected test file.",
  "reasoning": { "effort": "high" }
}
```

Overwrite TEST_FILE_PATH with the fixed tests. Increment round counter. Go back to Phase 2.

**If FAIL and round == 3:**

Act as TRIAGE. Analyse:
- Are the failures due to missing dependencies? (suggest `pip install` / `npm install` fix)
- Are the failures due to import errors? (fix import paths)
- Are the failures due to wrong mocking strategy? (suggest correct approach)
- Are the failures due to the source code having bugs? (flag to user)

Display diagnosis and apply one final fix attempt. If still failing after round 3 correction, halt.

**If FAIL after round 4:**
```
## 🛑 Max Rounds Reached
```
Show final test output and triage summary. Do NOT delete the test file.

---

### Phase 4 — Summary

Display:
```
## ✅ Unit Tests Complete

| Item | Value |
|------|-------|
| Source file | <FILE_PATH> |
| Test file | <TEST_FILE_PATH> |
| Framework | <FRAMEWORK> |
| Tests passed | N |
| Rounds needed | N |

**Coverage areas:**
- <bullet: what happy paths were tested>
- <bullet: what edge cases were covered>
- <bullet: what was mocked>

**To run again:**
\`\`\`bash
<run command>
\`\`\`
```
