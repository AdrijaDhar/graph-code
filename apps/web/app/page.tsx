import { Button, Card, Muted, PageHeading } from "./components/ui";
import { GitHubIcon, GitBranchIcon, NetworkIcon, SearchIcon, ShieldIcon, SparkleIcon } from "./components/Icon";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FEATURES = [
  { icon: <GitBranchIcon />, text: "Polyglot: Python, TS/JS, Go, Java, Rust, C/C++" },
  { icon: <NetworkIcon />, text: "Dual store: Memgraph + RocksDB snapshots and vectors" },
  { icon: <SearchIcon />, text: "Live file watcher and MiniLM semantic search" },
  { icon: <ShieldIcon />, text: "Teams, API keys, usage quotas (Stripe test mode)" },
];

export default function Home() {
  return (
    <div>
      <div className="inline-flex items-center gap-1.5 text-xs font-medium text-[#8ab4ff] bg-[#3b7bf6]/10 border border-[#3b7bf6]/20 rounded-full px-3 py-1 mb-4">
        <SparkleIcon className="w-3 h-3" />
        Structural context for LLM coding agents
      </div>
      <PageHeading>High-performance Graph-Code Copilot</PageHeading>
      <Muted className="text-base mt-3 max-w-xl">
        Cursor and Copilot only see a few open files. Graph-Code parses the whole repo with Tree-sitter, stores
        CALLS / IMPORTS / INHERITS in a graph, and feeds structural context to the agent via MCP.
      </Muted>
      <p className="text-[#e8eefc]/80 mt-3 max-w-xl">
        A change in <code className="bg-white/[0.06] px-1.5 py-0.5 rounded text-sm text-[#8ab4ff]">utils.py</code> that
        breaks a controller five folders away is a shortest-path query, not a guess.
      </p>

      <Card>
        <a href={`${API}/v1/auth/github`}>
          <Button className="flex items-center gap-2">
            <GitHubIcon />
            Sign in with GitHub
          </Button>
        </a>
        <ul className="mt-5 space-y-3">
          {FEATURES.map((f, i) => (
            <li key={i} className="flex items-center gap-2.5 text-sm text-[#e8eefc]/75">
              <span className="text-[#3b7bf6] shrink-0">{f.icon}</span>
              {f.text}
            </li>
          ))}
        </ul>
      </Card>

      <p className="mt-5 text-sm">
        <a href="/impact" className="text-[#8ab4ff] hover:text-white transition-colors">
          See public impact numbers →
        </a>
      </p>
    </div>
  );
}
