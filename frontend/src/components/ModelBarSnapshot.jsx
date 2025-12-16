import './ModelBarSnapshot.css';

function ModelBarSnapshot({ models }) {
  if (!models || models.length === 0) {
    return null;
  }

  const getShortName = (model) => {
    const parts = model.split('/');
    return parts[parts.length - 1];
  };

  const buildTitle = (model, notes, canBrowse, canCode, isChairman) => {
    const extras = ['Models used for this query (read-only)'];
    if (notes) {
      extras.push(notes);
    }
    if (canBrowse) {
      extras.push('Can browse web');
    }
    if (canCode) {
      extras.push('Coding model');
    }
    if (isChairman) {
      extras.push('Acts as chairman');
    }
    return extras.join('; ');
  };

  return (
    <div className="model-bar-snapshot">
      <div className="snapshot-label">Models used:</div>
      <div className="snapshot-models">
        {models.map(({ model, enabled, notes, expensive, can_browse: canBrowse, can_code: canCode, is_chairman: isChairman }) => (
          <span
            key={model}
            className={`model-snapshot ${enabled ? 'enabled' : 'disabled'}${notes ? ' has-note' : ''}`}
            title={buildTitle(model, notes, canBrowse, canCode, isChairman)}
          >
            {isChairman && (
              <span
                className="model-chairman-icon"
                role="img"
                aria-label="Chairman model"
              >
                ⚖
              </span>
            )}
            {expensive && (
              <span
                className="model-expensive-icon"
                role="img"
                aria-label="Expensive model"
              >
                💰
              </span>
            )}
            {canBrowse && (
              <span
                className="model-browse-icon"
                role="img"
                aria-label="Can browse web"
              >
                🔎
              </span>
            )}
            {canCode && (
              <span
                className="model-code-icon"
                role="img"
                aria-label="Coding model"
              >
                💻
              </span>
            )}
            <span className="model-snapshot-name">
              {getShortName(model)}
            </span>
            {notes && <span className="model-note">{notes}</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

export default ModelBarSnapshot;
