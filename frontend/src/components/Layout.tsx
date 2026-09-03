import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  ["Home", "/"],
  ["Data Explorer", "/explore"],
  ["Metadata", "/metadata"],
  ["Validation", "/validation"],
  ["Harmonisation", "/harmonization"],
  ["Architecture", "/architecture"],
  ["API", "/api"],
  ["About", "/about"]
];

export default function Layout() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="site-header">
        <div className="identity-bar">
          <NavLink to="/" className="wordmark" aria-label="Pan-African SDMX Trade Data Hub home">
            <span className="wordmark-mark" aria-hidden="true">SDMX</span>
            <span>
              <strong>Pan-African SDMX Trade Data Hub</strong>
              <small>Harmonisation, validation and dissemination of African merchandise trade statistics</small>
            </span>
          </NavLink>
          <p className="header-disclaimer">Independent portfolio demonstration — not an official AU/STATAFRIC platform.</p>
        </div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navigation.map(([label, path]) => (
            <NavLink key={path} to={path} end={path === "/"} className={({ isActive }) => isActive ? "active" : ""}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main id="main-content"><Outlet /></main>
      <footer className="site-footer">
        <div>
          <strong>Pan-African SDMX Trade Data Hub</strong>
          <p>Source data: UN Statistics Division / UN Comtrade.</p>
        </div>
        <p>This independent portfolio demonstration is not affiliated with or endorsed by the African Union or STATAFRIC.</p>
      </footer>
    </div>
  );
}
