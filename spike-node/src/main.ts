/** CLIConductor Spike — Node.js + Express + ws
 *
 * Milestone 1: 单 Worker 可启动，stdout 可读
 */

import { spawn } from "child_process";
import { createInterface } from "readline";

async function main() {
  console.log("CLIConductor Spike (Node.js)");

  // 启动 cbc 子进程
  const child = spawn("cbc", [
    "-p",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "-y",
  ], {
    stdio: ["pipe", "pipe", "pipe"],
    shell: true,
  });

  // 逐行读取 stdout
  const rl = createInterface({ input: child.stdout! });
  rl.on("line", (line: string) => {
    let event: any;
    try {
      event = JSON.parse(line);
    } catch {
      console.log(`[RAW] ${line.slice(0, 200)}`);
      return;
    }
    const t = event.type;
    if (t === "assistant") {
      const content = event.message?.content ?? [];
      for (const block of content) {
        if (block.type === "text") {
          console.log(`[TEXT] ${block.text}`);
        } else if (block.type === "thinking") {
          console.log(`[THINK] ${block.thinking.slice(0, 100)}...`);
        }
      }
    } else if (t === "result") {
      console.log(`[DONE] ${event.subtype}: ${event.result}`);
      child.kill();
    }
  });

  child.stderr!.on("data", (d: Buffer) => process.stderr.write(d));

  child.on("spawn", () => {
    const msg = JSON.stringify({
      type: "user",
      message: {
        role: "user",
        content: [{ type: "text", text: "Say 'spike node OK' and nothing else." }],
      },
    });
    child.stdin!.write(msg + "\n");
  });

  await new Promise<void>((resolve) => child.on("close", resolve));
  console.log("Spike completed.");
}

main();
