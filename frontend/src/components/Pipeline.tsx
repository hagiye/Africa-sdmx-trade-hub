const stages = ["UN Comtrade", "UNSD:IMTS", "Validation", "Harmonisation", "AFR_TRADE", "PostgreSQL", "REST API"];

export default function Pipeline() {
  return (
    <div className="pipeline" aria-label={stages.join(" to ")}>
      {stages.map((stage, index) => (
        <div className="pipeline-segment" key={stage}>
          <span>{stage}</span>
          {index < stages.length - 1 && <b aria-hidden="true">→</b>}
        </div>
      ))}
    </div>
  );
}
