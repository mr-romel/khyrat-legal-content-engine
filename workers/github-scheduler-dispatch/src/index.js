const OWNER = "mr-romel";
const REPO = "khyrat-legal-content-engine";
const WORKFLOW = "publish-scheduled.yml";
const REF = "main";
const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
const ACTIVE_WINDOW_MS = 20 * 60 * 1000;

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
};

async function dispatch(env) {
  if (!env.GITHUB_DISPATCH_TOKEN) {
    throw new Error("GITHUB_DISPATCH_TOKEN is missing");
  }

  const headers = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "khyrat-github-scheduler-dispatch",
  };

  console.log(`Scheduler heartbeat: ${new Date().toISOString()}`);

  const runs = await github(
    `${API}/actions/workflows/${WORKFLOW}/runs?branch=${REF}&event=workflow_dispatch&per_page=10`,
    { headers },
  );

  const now = Date.now();
  const active = (runs.workflow_runs || []).find((run) => {
    if (run.status !== "queued" && run.status !== "in_progress") return false;
    const stamp = Date.parse(run.updated_at || run.created_at || "");
    return Number.isFinite(stamp) && now - stamp < ACTIVE_WINDOW_MS;
  });

  if (active) {
    console.log(
      `Publisher active recently (${active.status}, ${active.id}); skipping duplicate dispatch.`,
    );
    return;
  }

  const response = await fetch(`${API}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ ref: REF }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub dispatch failed: ${response.status} ${body.slice(0, 500)}`);
  }

  console.log(`Publisher dispatched successfully at ${new Date().toISOString()}`);
}

async function github(url, options) {
  const response = await fetch(url, { ...options, method: "GET" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub scheduler check failed: ${response.status} ${body.slice(0, 500)}`);
  }
  return response.json();
}
