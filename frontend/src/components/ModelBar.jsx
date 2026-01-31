import { useState, useEffect } from 'react';
import { api } from '../api';
import './ModelBar.css';

function ModelBar() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [buttonMode, setButtonMode] = useState('Clear'); // 'Clear' or 'Set'

  useEffect(() => {
    loadModels();
  }, []);

  const calculateButtonMode = (modelsList) => {
    const anyEnabled = modelsList.some(m => m.enabled);
    if (!anyEnabled) {
      return 'Set';
    }
    const nonExpensiveModels = modelsList.filter(m => !m.expensive);
    const expensiveModels = modelsList.filter(m => m.expensive);
    const allNonExpensiveEnabled = nonExpensiveModels.length > 0 && nonExpensiveModels.every(m => m.enabled);
    const anyExpensiveDisabled = expensiveModels.some(m => !m.enabled);
    
    if (allNonExpensiveEnabled && anyExpensiveDisabled) {
      return '💰';
    }
    return 'Clear';
  };

  const loadModels = async () => {
    try {
      const data = await api.getModels();
      setModels(data);
      setButtonMode(calculateButtonMode(data));
    } catch (error) {
      console.error('Failed to load models:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (event, model, currentEnabled) => {
    try {
      if (event.shiftKey) {
        await api.setChairman(model);
        setModels(prevModels => prevModels.map(m => ({
          ...m,
          is_chairman: m.model === model,
        })));
        return;
      }

      await api.toggleModel(model, !currentEnabled);
      setModels(prevModels => {
        const updatedModels = prevModels.map(m =>
          m.model === model ? { ...m, enabled: !currentEnabled } : m
        );
        setButtonMode(calculateButtonMode(updatedModels));
        return updatedModels;
      });
    } catch (error) {
      console.error('Failed to update model state:', error);
    }
  };

  const handleClearSet = async () => {
    try {
      if (buttonMode === 'Clear') {
        // Disable all models
        await Promise.all(
          models.map(m => api.toggleModel(m.model, false))
        );
        setModels(prevModels => {
          const updatedModels = prevModels.map(m => ({ ...m, enabled: false }));
          setButtonMode(calculateButtonMode(updatedModels));
          return updatedModels;
        });
      } else if (buttonMode === 'Set') {
        // Enable only non-expensive models
        await Promise.all(
          models.map(m => api.toggleModel(m.model, !m.expensive))
        );
        setModels(prevModels => {
          const updatedModels = prevModels.map(m => ({
            ...m,
            enabled: !m.expensive
          }));
          setButtonMode(calculateButtonMode(updatedModels));
          return updatedModels;
        });
      } else if (buttonMode === '💰') {
        // Enable expensive models (non-expensive already enabled)
        await Promise.all(
          models.filter(m => m.expensive).map(m => api.toggleModel(m.model, true))
        );
        setModels(prevModels => {
          const updatedModels = prevModels.map(m => ({
            ...m,
            enabled: true
          }));
          setButtonMode(calculateButtonMode(updatedModels));
          return updatedModels;
        });
      }
    } catch (error) {
      console.error('Failed to update all models:', error);
    }
  };

  const getShortName = (model) => {
    const parts = model.split('/');
    return parts[parts.length - 1];
  };

  const buildTitle = (model, notes, canBrowse, canCode, isChairman) => {
    const extras = [];
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
    extras.push('Shift+click to set chairman');
    return extras.join('; ');
  };

  if (loading) {
    return <div className="model-bar">Loading models...</div>;
  }

  return (
    <div className="model-bar">
      <button
        type="button"
        className="clear-set-button"
        onClick={handleClearSet}
        title={
          buttonMode === 'Clear' ? 'Disable all models' :
          buttonMode === '💰' ? 'Enable expensive models' :
          'Enable all non-expensive models'
        }
      >
        {buttonMode}
      </button>
      {models.map(({ model, enabled, notes, expensive, can_browse: canBrowse, can_code: canCode, is_chairman: isChairman }) => (
        <button
          type="button"
          key={model}
          className={`model-toggle ${enabled ? 'enabled' : 'disabled'}${notes ? ' has-note' : ''}`}
          onClick={(event) => handleToggle(event, model, enabled)}
          title={buildTitle(model, notes, canBrowse, canCode, isChairman)}
        >
          {isChairman && (
            <span
              className="model-chairman-icon"
              role="img"
              aria-label="Chairman model"
              title="Acts as chairman"
            >
              ⚖
            </span>
          )}
          {expensive && (
            <span
              className="model-expensive-icon"
              role="img"
              aria-label="Expensive model"
              title="Expensive"
            >
              💰
            </span>
          )}
          {canBrowse && (
            <span
              className="model-browse-icon"
              role="img"
              aria-label="Can browse web"
              title="Can browse web"
            >
              🔎
            </span>
          )}
          {canCode && (
            <span
              className="model-code-icon"
              role="img"
              aria-label="Coding model"
              title="Coding model"
            >
              💻
            </span>
          )}
          <span
            className="model-toggle-name"
            aria-label={
              canBrowse
                ? `${getShortName(model)} (can browse web${isChairman ? '; chairman' : ''})`
                : isChairman
                ? `${getShortName(model)} (chairman)`
                : undefined
            }
          >
            {getShortName(model)}
          </span>
          {notes && <span className="model-note">{notes}</span>}
        </button>
      ))}
    </div>
  );
}

export default ModelBar;
