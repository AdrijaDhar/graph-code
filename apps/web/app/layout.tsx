export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "ui-sans-serif, system-ui", margin: 0, background: "#0b1020", color: "#e8eefc" }}>
        <header style={{ padding: "16px 24px", borderBottom: "1px solid #243" }}>
          <a href="/" style={{ color: "#9cf", textDecoration: "none", fontWeight: 700 }}>
            Graph-Code
          </a>
          {"  "}
          <a href="/impact" style={{ color: "#9cf", marginLeft: 16 }}>
            Impact
          </a>
          <a href="/app" style={{ color: "#9cf", marginLeft: 16 }}>
            Dashboard
          </a>
          <a href="/admin" style={{ color: "#9cf", marginLeft: 16 }}>
            Admin
          </a>
        </header>
        <main style={{ padding: 24, maxWidth: 960, margin: "0 auto" }}>{children}</main>
      </body>
    </html>
  );
}
