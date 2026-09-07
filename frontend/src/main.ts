import RuntimeForceGraph3D, {
  type ConfigOptions,
  type ForceGraph3DInstance,
  type LinkObject,
  type NodeObject,
} from "3d-force-graph";
import {
  SCHEMA_VERSION,
  type ApiErrorResponse,
  type ExpandResponse,
  type GraphLink,
  type GraphNode,
  type HealthResponse,
  type QueryRequest,
  type QueryResponse,
  type SchemaVersion,
  type SnapshotResponse,
  type SnapshotStats,
} from "./types";

type ForceGraph3DConstructor = {
  new <
    NodeType extends NodeObject = NodeObject,
    LinkType extends LinkObject<NodeType> = LinkObject<NodeType>,
  >(
    element: HTMLElement,
    configOptions?: ConfigOptions,
  ): ForceGraph3DInstance<NodeType, LinkType>;
};

// The installed package exposes the generic instance but erases the generic
// constructor parameters on its default export. Keep that correction at the
// library boundary so the graph and all callbacks remain strongly typed.
const ForceGraph3D = RuntimeForceGraph3D as ForceGraph3DConstructor;

const COLORS = {
  entity: "#ffffff",
  chunk: "rgba(255, 255, 255, 0.55)",
  linkSemantic: "rgba(255, 255, 255, 0.32)",
  linkProvenance: "rgba(255, 255, 255, 0.10)",
  highlight: "#ffffff",
  highlightLink: "rgba(255, 255, 255, 0.85)",
  dim: "rgba(255, 255, 255, 0.06)",
  dimLink: "rgba(255, 255, 255, 0.03)",
  particle: "#ffffff",
};

function requireElement<ElementType extends Element>(selector: string): ElementType {
  const element = document.querySelector<ElementType>(selector);
  if (!element) throw new Error(`Elemento UI mancante: ${selector}`);
  return element;
}

function createApiBaseUrl(configuredValue: string | undefined): URL {
  const configured = configuredValue?.trim() || "/api";
  const hasScheme = /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(configured);
  const source = hasScheme ? configured : `/${configured.replace(/^\/+/, "")}`;
  const url = new URL(source, window.location.origin);

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`VITE_API_BASE non valido: protocollo ${url.protocol}`);
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("VITE_API_BASE non può contenere credenziali, query o fragment");
  }

  url.pathname = `${url.pathname.replace(/\/+$/, "")}/`;
  return url;
}

const API_BASE_URL = createApiBaseUrl(import.meta.env.VITE_API_BASE);

function apiUrl(path: string, query?: URLSearchParams): string {
  const url = new URL(path.replace(/^\/+/, ""), API_BASE_URL);
  if (query) url.search = query.toString();
  return url.toString();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isApiErrorResponse(value: unknown): value is ApiErrorResponse {
  return isRecord(value) && "detail" in value;
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!isRecord(item)) return String(item);
        const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
        const message = typeof item.msg === "string" ? item.msg : JSON.stringify(item);
        return location ? `${location}: ${message}` : message;
      })
      .join("; ");
  }
  if (detail == null) return "";
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

async function createHttpError(response: Response): Promise<Error> {
  let detail = "";
  const body = await response.text();
  if (body) {
    try {
      const payload: unknown = JSON.parse(body);
      if (isApiErrorResponse(payload)) {
        detail = formatDetail(payload.detail);
      } else {
        detail = formatDetail(payload);
      }
    } catch {
      detail = body.trim();
    }
  }

  const status = `${response.status} ${response.statusText}`.trim();
  return new Error(detail ? `${status} · ${detail}` : status);
}

function assertSchemaVersion(
  payload: unknown,
  endpoint: string,
): asserts payload is { schema_version: SchemaVersion } {
  const received = isRecord(payload) ? payload.schema_version : undefined;
  if (received !== SCHEMA_VERSION) {
    const value = received == null ? "mancante" : JSON.stringify(received);
    throw new Error(
      `Schema API incompatibile per ${endpoint}: atteso ${SCHEMA_VERSION}, ricevuto ${value}`,
    );
  }
}

async function fetchVersioned<ResponseType extends { schema_version: SchemaVersion }>(
  endpoint: string,
  init?: RequestInit,
  query?: URLSearchParams,
): Promise<ResponseType> {
  const response = await fetch(apiUrl(endpoint, query), init);
  if (!response.ok) throw await createHttpError(response);

  const payload: unknown = await response.json();
  assertSchemaVersion(payload, endpoint);
  return payload as ResponseType;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

let highlightedIds = new Set<string>();
let visibleNodeIds = new Set<string>();
let activeModel = "";
let sceneCounts: { nodes: number; links: number } | null = null;
let healthState:
  | { status: "loading" }
  | { status: HealthResponse["status"] }
  | { status: "error"; message: string } = { status: "loading" };
let lastQueryVisibility: {
  citedNodeIds: string[];
  highlightNodeIds: string[];
} | null = null;
let graphRequestGeneration = 0;
let graphAbortController: AbortController | null = null;
let queryRequestGeneration = 0;
let queryAbortController: AbortController | null = null;
let previewRequestGeneration = 0;
let previewAbortController: AbortController | null = null;

const elGraph = requireElement<HTMLElement>("#graph");
const elStats = requireElement<HTMLElement>("#stats");
const elHover = requireElement<HTMLElement>("#hover");
const elSceneMeta = requireElement<HTMLElement>("#scene-meta");
const elChunks = requireElement<HTMLInputElement>("#opt-chunks");
const elNoisy = requireElement<HTMLInputElement>("#opt-noisy");
const elMinDeg = requireElement<HTMLInputElement>("#opt-mindeg");
const elMinDegVal = requireElement<HTMLElement>("#opt-mindeg-val");
const elReload = requireElement<HTMLButtonElement>("#reload");
const elQ = requireElement<HTMLTextAreaElement>("#q");
const elAsk = requireElement<HTMLButtonElement>("#ask");
const elAskStatus = requireElement<HTMLElement>("#ask-status");
const elAnswerBox = requireElement<HTMLElement>("#answer-box");
const elAnswer = requireElement<HTMLElement>("#answer");
const elCited = requireElement<HTMLElement>("#cited");
const elClearHighlight = requireElement<HTMLButtonElement>("#clear-highlight");
const elPreview = requireElement<HTMLElement>("#preview");
const elPreviewTitle = requireElement<HTMLElement>("#preview-title");
const elPreviewBody = requireElement<HTMLElement>("#preview-body");
const elPreviewClose = requireElement<HTMLButtonElement>("#preview-close");

const Graph = new ForceGraph3D<GraphNode, GraphLink>(elGraph)
  .backgroundColor("#000000")
  .nodeRelSize(4)
  .nodeLabel(
    (node) =>
      `<span style="font-family: inherit; font-size: 12px; color: #fff; background: rgba(0,0,0,0.85); padding: 4px 8px; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px;">${escapeHtml(
        node.name ?? node.file_name ?? node.id,
      )}</span>`,
  )
  .nodeColor((node) => {
    if (highlightedIds.size > 0) {
      return highlightedIds.has(node.id) ? COLORS.highlight : COLORS.dim;
    }
    return node.type === "entity" ? COLORS.entity : COLORS.chunk;
  })
  .nodeOpacity(0.95)
  .nodeVal((node) => {
    if (node.type === "chunk") return 2;
    return Math.max(1.5, Math.min(10, (node.degree ?? 1) * 1.1));
  })
  .linkColor((link) => {
    if (highlightedIds.size > 0) {
      const sourceId = typeof link.source === "string" ? link.source : link.source.id;
      const targetId = typeof link.target === "string" ? link.target : link.target.id;
      const highlighted = highlightedIds.has(sourceId) || highlightedIds.has(targetId);
      return highlighted ? COLORS.highlightLink : COLORS.dimLink;
    }
    return link.kind === "provenance" ? COLORS.linkProvenance : COLORS.linkSemantic;
  })
  .linkWidth((link) => (link.kind === "provenance" ? 0.4 : 0.8))
  .linkDirectionalParticles(1)
  .linkDirectionalParticleSpeed(0.004)
  .linkDirectionalParticleWidth(1.4)
  .linkDirectionalParticleColor(() => COLORS.particle)
  .onNodeHover((node) => showHover(node))
  .onNodeClick((node) => openPreview(node));

// Idle rotation — gentle, breathing constellation.
let userInteracting = false;
let lastInteractionAt = 0;
let theta: number | null = null;
const IDLE_AFTER_MS = 2200;
const ROT_SPEED = 0.0012;

elGraph.addEventListener("pointerdown", () => {
  userInteracting = true;
  lastInteractionAt = Date.now();
});
window.addEventListener("pointerup", () => {
  userInteracting = false;
  lastInteractionAt = Date.now();
});
elGraph.addEventListener(
  "wheel",
  () => {
    lastInteractionAt = Date.now();
  },
  { passive: true },
);

function tickIdle() {
  requestAnimationFrame(tickIdle);
  if (userInteracting) return;
  if (highlightedIds.size > 0) return;
  if (Date.now() - lastInteractionAt < IDLE_AFTER_MS) return;
  const position = Graph.cameraPosition();
  const distance = Math.hypot(position.x, position.z);
  if (distance < 1) return;
  if (theta === null) theta = Math.atan2(position.x, position.z);
  theta += ROT_SPEED;
  Graph.cameraPosition(
    {
      x: Math.sin(theta) * distance,
      y: position.y,
      z: Math.cos(theta) * distance,
    },
    undefined,
    0,
  );
}
requestAnimationFrame(tickIdle);

function renderSceneMeta() {
  const counts = sceneCounts
    ? `${sceneCounts.nodes} nodes · ${sceneCounts.links} links`
    : "graph loading…";
  const health =
    healthState.status === "error"
      ? `health error · ${healthState.message}`
      : healthState.status === "loading"
        ? "health loading…"
        : `health ${healthState.status}`;
  const model = activeModel || "model unavailable";

  elSceneMeta.innerHTML = `
    <div>${escapeHtml(counts)}</div>
    <div>kwipu · ${escapeHtml(health)} · ${escapeHtml(model)}</div>
  `;
}

async function loadHealth() {
  try {
    const health = await fetchVersioned<HealthResponse>("health");
    activeModel = health.llm_model;
    healthState = { status: health.status };
  } catch (error) {
    activeModel = "";
    healthState = { status: "error", message: errorMessage(error) };
  }
  renderSceneMeta();
  if (lastQueryVisibility) refreshQueryVisibility();
}

async function loadGraph() {
  const requestGeneration = ++graphRequestGeneration;
  graphAbortController?.abort();
  const controller = new AbortController();
  graphAbortController = controller;
  const params = new URLSearchParams({
    include_chunks: String(elChunks.checked),
    drop_noisy: String(elNoisy.checked),
    min_degree: elMinDeg.value,
  });
  elStats.innerHTML = `<span class="key">loading…</span>`;
  try {
    const snapshot = await fetchVersioned<SnapshotResponse>(
      "graph/snapshot",
      { signal: controller.signal },
      params,
    );
    if (requestGeneration !== graphRequestGeneration) return;
    Graph.graphData({ nodes: snapshot.nodes, links: snapshot.links });
    visibleNodeIds = new Set(snapshot.nodes.map((node) => node.id));
    sceneCounts = { nodes: snapshot.nodes.length, links: snapshot.links.length };
    elStats.innerHTML = formatStats(snapshot.stats);
    renderSceneMeta();
    if (lastQueryVisibility) refreshQueryVisibility();
  } catch (error) {
    if (requestGeneration !== graphRequestGeneration) return;
    elStats.innerHTML = `<span class="key">error: ${escapeHtml(errorMessage(error))}</span>`;
  } finally {
    if (graphAbortController === controller) graphAbortController = null;
  }
}

function formatStats(stats: SnapshotStats): string {
  const row = (key: string, value: string | number) =>
    `<span class="key">${key.padEnd(14, " ")}</span><span class="val">${value}</span>\n`;
  return [
    row("raw nodes", stats.total_nodes_raw),
    row("raw relations", stats.total_relations_raw),
    row("kept nodes", stats.kept_nodes),
    row("kept links", stats.kept_links),
    row("skipped noisy", stats.skipped_noisy),
  ].join("");
}

function showHover(node: GraphNode | null) {
  if (!node) {
    elHover.innerHTML = `<div class="empty">hover a node…</div>`;
    return;
  }
  const frontmatterRows = Object.entries(node.fm)
    .map(
      ([key, value]) =>
        `<div><span class="k">${escapeHtml(key)}</span> · ${escapeHtml(String(value))}</div>`,
    )
    .join("");
  elHover.innerHTML = `
    <span class="name">${escapeHtml(node.name ?? node.file_name ?? node.id)}</span>
    <div class="meta">
      <div><span class="k">type</span> · ${node.type}${
        node.degree != null ? ` · degree ${node.degree}` : ""
      }</div>
      ${
        node.file_name
          ? `<div><span class="k">file</span> · ${escapeHtml(node.file_name)}</div>`
          : ""
      }
      ${frontmatterRows}
    </div>
  `;
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character]!,
  );
}

function uniqueIds(ids: string[]): string[] {
  return [...new Set(ids)];
}

function refreshQueryVisibility() {
  if (!lastQueryVisibility) return;

  const visibleSources = lastQueryVisibility.citedNodeIds.filter((id) => visibleNodeIds.has(id));
  const visibleHighlights = lastQueryVisibility.highlightNodeIds.filter((id) =>
    visibleNodeIds.has(id),
  );
  highlightNodes(visibleHighlights);

  const modelLabel = activeModel ? ` · ${activeModel}` : "";
  elAskStatus.textContent =
    `${visibleSources.length}/${lastQueryVisibility.citedNodeIds.length} source(s) visible · ` +
    `${visibleHighlights.length}/${lastQueryVisibility.highlightNodeIds.length} highlight(s) visible` +
    modelLabel;
}

async function askQuestion() {
  const question = elQ.value.trim();
  if (!question) return;
  const requestGeneration = ++queryRequestGeneration;
  queryAbortController?.abort();
  const controller = new AbortController();
  queryAbortController = controller;

  elAsk.disabled = true;
  elAskStatus.classList.add("thinking");
  elAskStatus.textContent = "thinking";
  lastQueryVisibility = null;
  highlightNodes([]);
  elAnswerBox.hidden = true;
  try {
    const request: QueryRequest = { q: question };
    const data = await fetchVersioned<QueryResponse>("query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: controller.signal,
    });
    if (requestGeneration !== queryRequestGeneration) return;
    elAnswer.innerHTML = renderMarkdown(data.answer || "(no answer)");
    elCited.innerHTML = data.cited_files
      .map((fileName) => `<span class="chip">${escapeHtml(fileName)}</span>`)
      .join("");
    elAnswerBox.hidden = false;
    elAskStatus.classList.remove("thinking");

    const citedNodeIds = uniqueIds(data.cited_node_ids);
    const requestedHighlights = uniqueIds(data.highlight_node_ids);
    lastQueryVisibility = {
      citedNodeIds,
      highlightNodeIds: requestedHighlights.length > 0 ? requestedHighlights : citedNodeIds,
    };
    refreshQueryVisibility();
  } catch (error) {
    if (requestGeneration !== queryRequestGeneration) return;
    elAskStatus.classList.remove("thinking");
    elAskStatus.textContent = `error · ${errorMessage(error)}`;
  } finally {
    if (queryAbortController === controller) {
      queryAbortController = null;
      elAsk.disabled = false;
    }
  }
}

// Lightweight markdown: **bold** only — keeps the panel clean.
function renderMarkdown(source: string): string {
  return escapeHtml(source).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function highlightNodes(ids: string[]) {
  highlightedIds = new Set(ids);
  Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor());
}

function clearHighlight() {
  queryRequestGeneration += 1;
  queryAbortController?.abort();
  queryAbortController = null;
  elAsk.disabled = false;
  elAskStatus.classList.remove("thinking");
  lastQueryVisibility = null;
  highlightNodes([]);
  elAnswerBox.hidden = true;
  elAskStatus.textContent = "";
}

elAsk.addEventListener("click", askQuestion);
elQ.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    askQuestion();
  }
});
elClearHighlight.addEventListener("click", clearHighlight);
elPreviewClose.addEventListener("click", closePreview);

async function openPreview(node: GraphNode) {
  const requestGeneration = ++previewRequestGeneration;
  previewAbortController?.abort();
  const controller = new AbortController();
  previewAbortController = controller;

  // Tween camera toward the node so the click feels meaningful.
  if (node.x != null && node.y != null && node.z != null) {
    const distance = 140;
    const radialDistance = Math.max(1, Math.hypot(node.x, node.y, node.z));
    const ratio = 1 + distance / radialDistance;
    Graph.cameraPosition(
      { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
      { x: node.x, y: node.y, z: node.z },
      800,
    );
  }
  elPreviewTitle.textContent = node.name ?? node.file_name ?? node.id;
  elPreviewBody.innerHTML = `<em style="color: var(--fg-mute)">loading…</em>`;
  elPreview.hidden = false;
  try {
    const params = new URLSearchParams({ node_id: node.id });
    const data = await fetchVersioned<ExpandResponse>(
      "expand",
      { signal: controller.signal },
      params,
    );
    if (requestGeneration !== previewRequestGeneration) return;
    elPreviewTitle.textContent = data.file_name;
    elPreviewBody.innerHTML = `
      ${renderMarkdownBlock(data.markdown)}
      <div class="preview-meta">${escapeHtml(data.file_path)}</div>
    `;
  } catch (error) {
    if (requestGeneration !== previewRequestGeneration) return;
    elPreviewBody.innerHTML = `<em style="color: var(--fg-mute)">${escapeHtml(
      errorMessage(error),
    )}</em>`;
  } finally {
    if (previewAbortController === controller) previewAbortController = null;
  }
}

function closePreview() {
  previewRequestGeneration += 1;
  previewAbortController?.abort();
  previewAbortController = null;
  elPreview.hidden = true;
}

function renderMarkdownBlock(source: string): string {
  // Lightweight markdown — enough for personal notes.
  let html = escapeHtml(source);
  html = html.replace(/^---\n([\s\S]*?)\n---\n?/, (_, yaml: string) => {
    const rows = yaml
      .split("\n")
      .filter(Boolean)
      .map((line) => `<div>${line}</div>`)
      .join("");
    return `<div class="preview-meta" style="margin: 0 0 14px; border-top:none; padding-top:0">${rows}</div>`;
  });
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  html = html.replace(/```([\s\S]*?)```/g, (_, code: string) => `<pre>${code}</pre>`);
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
  html = html.replace(/\[\[([^\]]+)\]\]/g, '<a href="#">$1</a>');
  html = html.replace(/\n\n/g, "</p><p>");
  return `<p>${html}</p>`;
}

elReload.addEventListener("click", loadGraph);
elChunks.addEventListener("change", loadGraph);
elNoisy.addEventListener("change", loadGraph);
elMinDeg.addEventListener("input", () => {
  elMinDegVal.textContent = elMinDeg.value;
});
elMinDeg.addEventListener("change", loadGraph);

window.addEventListener("resize", () => {
  Graph.width(elGraph.clientWidth).height(elGraph.clientHeight);
});

renderSceneMeta();
void (async () => {
  await loadHealth();
  await loadGraph();
})();

// Expose a few hooks for end-to-end tests / debugging.
Object.assign(window, {
  __kwipu: {
    Graph,
    openPreview,
    askQuestion,
    clearHighlight,
  },
});
