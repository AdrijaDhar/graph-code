import { Button, Card, Muted } from "../components/ui";
import { GitHubIcon, ShieldIcon } from "../components/Icon";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Login() {
  return (
    <div className="max-w-sm mx-auto mt-12 text-center">
      <div className="w-12 h-12 rounded-2xl bg-[#3b7bf6]/10 border border-[#3b7bf6]/20 flex items-center justify-center text-[#3b7bf6] mx-auto mb-4">
        <ShieldIcon className="w-6 h-6" />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-white mb-1">Log in</h1>
      <Card>
        <a href={`${API}/v1/auth/github`} className="block">
          <Button className="w-full flex items-center justify-center gap-2">
            <GitHubIcon />
            Continue with GitHub
          </Button>
        </a>
        <Muted className="mt-4">Without GitHub OAuth configured, the API issues a demo session.</Muted>
      </Card>
    </div>
  );
}
