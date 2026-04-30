const http = require("http");
const { spawn } = require("child_process");

const influxHost = process.env.INFLUX_HOST || "influxdb";
const influxPort = Number(process.env.INFLUX_PORT || 8086);
const maxAttempts = Number(process.env.INFLUX_WAIT_ATTEMPTS || 120);
const intervalMs = Number(process.env.INFLUX_WAIT_INTERVAL_MS || 2000);

function checkInflux() {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: influxHost,
        port: influxPort,
        path: "/health",
        timeout: 1500,
      },
      (res) => {
        resolve(res.statusCode >= 200 && res.statusCode < 300);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForInflux() {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await checkInflux();
    if (ok) {
      console.log(`[wait-for-influx] InfluxDB is healthy after ${attempt} attempt(s).`);
      return true;
    }
    console.log(`[wait-for-influx] Waiting for InfluxDB... (${attempt}/${maxAttempts})`);
    // eslint-disable-next-line no-await-in-loop
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

async function main() {
  const ready = await waitForInflux();
  if (!ready) {
    console.error("[wait-for-influx] InfluxDB did not become healthy in time.");
    process.exit(1);
  }

  const child = spawn("node-red", ["--userDir", "/data"], { stdio: "inherit" });
  child.on("exit", (code) => process.exit(code ?? 0));
}

main().catch((err) => {
  console.error("[wait-for-influx] Fatal error:", err);
  process.exit(1);
});
