const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  return (
    <div>
      <h1>High-performance Graph-Code Copilot</h1>
      <p>
        Cursor and Copilot only see a few open files. Graph-Code parses the whole repo with Tree-sitter, stores
        CALLS / IMPORTS / INHERITS in Memgraph, and feeds structural context to the agent via MCP.
      </p>
      <p>
        A change in <code>utils.py</code> that breaks a controller five folders away is a shortest-path query, not a
        guess.
      </p>
      <p>
        <a href={`${API}/v1/auth/github`} style={{ color: "#9cf" }}>
          Sign in with GitHub
        </a>
      </p>
      <ul>
        <li>Polyglot: Python, TS/JS, Go, Java, Rust, C/C++</li>
        <li>Dual store: Memgraph + RocksDB snapshots and vectors</li>
        <li>Live file watcher and MiniLM semantic search</li>
        <li>Teams, API keys, usage quotas (Stripe test mode)</li>
      </ul>
    </div>
  );
}
