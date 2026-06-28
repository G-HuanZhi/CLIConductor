/**
 * 试验：--resume + --model 组合，验证切换模型并保留对话历史
 *
 * 流程：
 * 1. Spawn cbc with --session-id test-switch-001, ask about a color
 * 2. Read session_id, send second message to confirm multi-turn
 * 3. Kill process
 * 4. Spawn with --resume test-switch-001 --model <different-model>, ask "what did I ask earlier?"
 * 5. Check if it remembers
 */

import { spawn } from "child_process";
import { createInterface } from "readline";

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function runCbc(args, messages, label) {
  return new Promise((resolve) => {
    const child = spawn("cbc", args, {
      stdio: ["pipe", "pipe", "pipe"],
      shell: true,
    });

    const events = [];
    let sessionId = null;
    let done = false;

    const rl = createInterface({ input: child.stdout });
    rl.on("line", (line) => {
      try {
        const e = JSON.parse(line);
        events.push(e);
        if (e.type === "system" && e.subtype === "init") {
          sessionId = e.session_id;
          console.log(`  [${label}] session_id: ${sessionId}`);
        }
        if (e.type === "result") {
          done = true;
          console.log(`  [${label}] result: ${e.subtype === "error_during_execution" ? "ERROR" : "OK"} - ${e.result?.substring(0, 80) || "(no result)"}`);
        }
      } catch {}
    });

    // Send messages one by one with delay
    async function send() {
      for (const msg of messages) {
        console.log(`  [${label}] sending: "${msg.substring(0, 50)}..."`);
        child.stdin.write(msg + "\n");
        await sleep(2000); // Wait between messages
      }
      // Don't close stdin - we want multi-turn
    }

    send();

    // Resolve after all messages processed or timeout
    let msgCount = 0;
    rl.on("line", () => {
      msgCount++;
    });

    setTimeout(() => {
      child.kill();
      resolve({ sessionId, events, exited: done });
    }, 30000);
  });
}

async function main() {
  const msg = (text) => JSON.stringify({
    type: "user",
    message: {
      role: "user",
      content: [{ type: "text", text }],
    },
  });

  console.log("\n=== Phase 1: Setup with glm-5.2 ===");
  const r1 = await runCbc(
    ["-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y", "--session-id", "test-switch-001", "--model", "glm-5.2"],
    [msg("remember this: my favorite color is blue, answer with 'ok'")],
    "setup"
  );
  console.log(`  Setup session: ${r1.sessionId}`);

  await sleep(2000);

  console.log("\n=== Phase 2: Resume with deepseek-v4-pro, ask recall question ===");
  const r2 = await runCbc(
    ["-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y", "--resume", "test-switch-001", "--model", "deepseek-v4-pro"],
    [msg("what is my favorite color? answer in one short sentence")],
    "resume"
  );

  // Check if result mentions "blue" (proves history persisted)
  const lastResult = r2.events.findLast(e => e.type === "result");
  const resultText = lastResult?.result || "";
  const remembered = /blue/i.test(resultText);

  console.log(`\n=== RESULT ===`);
  console.log(`  Full result: ${resultText.substring(0, 200)}`);
  console.log(`  Remembered? ${remembered ? "YES ✅" : "NO ❌"}`);
  console.log(`  Original session: ${r1.sessionId}`);
  console.log(`  Resume session:  ${r2.sessionId}`);

  process.exit(remembered ? 0 : 1);
}

main().catch(console.error);
