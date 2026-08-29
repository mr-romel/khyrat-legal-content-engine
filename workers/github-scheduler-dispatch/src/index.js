const OWNER = "mr-romel";
const REPO = "khyrat-legal-content-engine";
const WORKFLOW = "publish-scheduled.yml";
const REF = "main";
const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
const ACTIVE_WINDOW_MS = 20 * 60 * 1000;
const MAX_RETRIES = 3;
const RETRY_DELAYS_MS = [1500, 3500, 7000];

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({
        ok: true,
        service: "khyrat-github-scheduler-dispatch",
        workflow: WORKFLOW,
        ref: REF,
        cron: "*/15 * * * *",
        timestamp: new Date().toISOString(),
      }), { headers: { "content-type": "application/json; charset=utf-8" } });
    }
    return new Response("OK", { status: 200 });
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
    console.log(`Publisher active recently (${active.status}, ${active.id}); skipping duplicate dispatch.`);
    return;
  }

  const response = await retryFetch(`${API}/actions/workflows/${WORKFLOW}/dispatches`, {
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
  const response = await retryFetch(url, { ...options, method: "GET" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub scheduler check failed: ${response.status} ${body.slice(0, 500)}`);
  }
  return response.json();
}

async function retryFetch(url, options) {
  let lastResponse = null;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt += 1) {
    try {
      const response = await fetch(url, options);
      if (response.ok || !isRetryable(response.status) || attempt === MAX_RETRIES - 1) {
        return response;
      }
      lastResponse = response;
      const retryAfter = Number(response.headers.get("Retry-After"));
      const delay = Number.isFinite(retryAfter) && retryAfter > 0
        ? Math.min(retryAfter * 1000, 15000)
        : RETRY_DELAYS_MS[attempt];
      console.log(`GitHub API ${response.status}; retry ${attempt + 1}/${MAX_RETRIES - 1} in ${delay}ms.`);
      await sleep(delay);
    } catch (error) {
      if (attempt === MAX_RETRIES - 1) throw error;
      const delay = RETRY_DELAYS_MS[attempt];
      console.log(`GitHub API network error; retry ${attempt + 1}/${MAX_RETRIES - 1} in ${delay}ms.`);
      await sleep(delay);
    }
  }
  return lastResponse;
}

function isRetryable(status) {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
