const { spawn } = require('child_process');

const cbc = spawn('cbc', [
  '-p',
  '--output-format', 'stream-json',
  '--input-format', 'stream-json',
  '--replay-user-messages',
  '-y',
], {
  cwd: 'd:/project/CLIConductor',
  stdio: ['pipe', 'pipe', 'pipe'],
  env: { ...process.env },
  shell: true,
});

let msgIndex = 0;
const messages = [
  'Say "hello from round 1" and nothing else.',
  'Say "hello from round 2" and nothing else.',
  'Say "hello from round 3" and nothing else.',
];

cbc.stderr.on('data', (d) => process.stderr.write(d));

cbc.stdout.on('data', (chunk) => {
  const text = chunk.toString();
  process.stdout.write(`[STDOUT] ${text}`);

  // Check if this looks like a complete assistant response followed by nothing
  const lines = text.trim().split('\n');
  for (const line of lines) {
    try {
      const obj = JSON.parse(line);
      if (obj.type === 'result') {
        console.log(`\n=== Turn ${msgIndex} completed (result type: ${obj.subtype}) ===\n`);
        // Send next message after a short delay
        if (msgIndex < messages.length) {
          const nextMsg = messages[msgIndex];
          const userInput = JSON.stringify({
            type: 'user',
            message: {
              role: 'user',
              content: [{ type: 'text', text: nextMsg }],
            },
          });
          console.log(`>>> Sending round ${msgIndex + 1}: ${nextMsg}`);
          cbc.stdin.write(userInput + '\n');
          msgIndex++;
        } else {
          console.log('\n>>> All rounds done, closing...');
          cbc.stdin.end();
        }
      }
    } catch {}
  }
});

cbc.on('spawn', () => {
  console.log('>>> cbc spawned, sending round 1...');
  const firstMsg = JSON.stringify({
    type: 'user',
    message: {
      role: 'user',
      content: [{ type: 'text', text: messages[0] }],
    },
  });
  cbc.stdin.write(firstMsg + '\n');
  msgIndex = 1;
});

cbc.on('close', (code) => {
  console.log(`\n>>> cbc exited with code ${code}`);
});
