// Use Agmente's recommended upstream transport, including its reconnect protocol.
import { startWebSocketServer } from '/opt/acp/node_modules/@rebornix/stdio-to-ws/dist/stdio-to-ws.js';

// Upstream 0.2.0 prettyPrintMessage bypasses its quiet flag. Never write ACP
// messages (prompts, tool results, session contents) to Kubernetes logs.
console.log = () => {};
startWebSocketServer({
  command: ['/opt/hermes/.venv/bin/hermes-acp'],
  port: 8766,
  quiet: true,
  persist: true,
  gracePeriodMs: 604800000,
});
