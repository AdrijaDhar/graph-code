"use client";
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Login() {
  return (
    <div>
      <h1>Log in</h1>
      <p>
        <a href={`${API}/v1/auth/github`} style={{ color: "#9cf" }}>
          Continue with GitHub
        </a>
      </p>
      <p>Without GitHub OAuth configured, the API issues a demo session.</p>
    </div>
  );
}
