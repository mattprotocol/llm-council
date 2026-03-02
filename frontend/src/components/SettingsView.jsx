import { useState, useEffect, useRef } from "react";
import { api } from "../api";
import "./SettingsView.css";

function SettingsView({ councils, onClose, onConfigChanged }) {
  const [activeTab, setActiveTab] = useState("models");
  const [status, setStatus] = useState({ type: "", message: "" });
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Models tab state
  const [models, setModels] = useState([]);
  const [chairman, setChairman] = useState("");
  const [titleModel, setTitleModel] = useState("");
  const [deliberationRounds, setDeliberationRounds] = useState(2);
  const [configLoaded, setConfigLoaded] = useState(false);

  // Councils tab state
  const [councilList, setCouncilList] = useState([]);
  const [selectedCouncilId, setSelectedCouncilId] = useState("");
  const [councilName, setCouncilName] = useState("");
  const [councilDescription, setCouncilDescription] = useState("");
  const [councilType, setCouncilType] = useState("persona");
  const [defaultModel, setDefaultModel] = useState("");
  const [personas, setPersonas] = useState([]);
  const [councilModels, setCouncilModels] = useState([]);
  const [rubric, setRubric] = useState([]);
  const [showNewCouncil, setShowNewCouncil] = useState(false);
  const [newCouncilId, setNewCouncilId] = useState("");
  const [newCouncilName, setNewCouncilName] = useState("");
  const [newCouncilType, setNewCouncilType] = useState("persona");

  // Import/Export state
  const fileInputRef = useRef(null);

  // Load config on mount
  useEffect(() => {
    loadConfig();
  }, []);

  // Load council details when selection changes
  useEffect(() => {
    if (selectedCouncilId) {
      loadCouncilDetail(selectedCouncilId);
    }
  }, [selectedCouncilId]);

  const loadConfig = async () => {
    try {
      const config = await api.getConfig();
      setModels(config.models || []);
      setChairman(config.chairman || "");
      setTitleModel(config.title_model || "");
      setDeliberationRounds(config.deliberation?.rounds || 2);
      setConfigLoaded(true);

      // Load councils
      const councilsList = await api.listCouncils();
      setCouncilList(councilsList);
      if (councilsList.length > 0 && !selectedCouncilId) {
        setSelectedCouncilId(councilsList[0].id);
      }
    } catch (err) {
      setStatus({ type: "error", message: "Failed to load config: " + err.message });
    }
  };

  const loadCouncilDetail = async (councilId) => {
    try {
      const response = await fetch(`/api/councils/${councilId}`);
      if (!response.ok) throw new Error("Failed to load council");
      const detail = await response.json();
      setCouncilName(detail.name || "");
      setCouncilDescription(detail.description || "");
      setCouncilType(detail.type || "persona");
      setDefaultModel(detail.default_model || "");
      setPersonas(detail.personas || []);
      setCouncilModels(detail.models || []);
      setRubric(detail.rubric || []);
    } catch (err) {
      setStatus({ type: "error", message: err.message });
    }
  };

  const markDirty = () => {
    setDirty(true);
    setStatus({ type: "unsaved", message: "Unsaved changes" });
  };

  // ========== Models Tab Handlers ==========

  const handleModelChange = (index, field, value) => {
    const updated = [...models];
    updated[index] = { ...updated[index], [field]: value };
    setModels(updated);
    markDirty();
  };

  const handleAddModel = () => {
    setModels([...models, { id: "", name: "" }]);
    markDirty();
  };

  const handleRemoveModel = (index) => {
    if (models.length <= 1) return;
    const updated = models.filter((_, i) => i !== index);
    setModels(updated);
    markDirty();
  };

  const handleSaveModels = async () => {
    setSaving(true);
    try {
      await api.updateConfig({
        models,
        chairman,
        title_model: titleModel,
        deliberation: { rounds: deliberationRounds, max_rounds: 5 },
      });
      setDirty(false);
      setStatus({ type: "success", message: "Models config saved" });
      if (onConfigChanged) onConfigChanged();
    } catch (err) {
      setStatus({ type: "error", message: err.message });
    }
    setSaving(false);
  };

  // ========== Councils Tab Handlers ==========

  const handlePersonaChange = (index, field, value) => {
    const updated = [...personas];
    updated[index] = { ...updated[index], [field]: value };
    setPersonas(updated);
    markDirty();
  };

  const handleAddPersona = () => {
    setPersonas([...personas, { model: defaultModel || models[0]?.id || "", role: "", prompt: "" }]);
    markDirty();
  };

  const handleRemovePersona = (index) => {
    if (personas.length <= 1) return;
    setPersonas(personas.filter((_, i) => i !== index));
    markDirty();
  };

  const handleSaveCouncil = async () => {
    setSaving(true);
    try {
      const data = {
        name: councilName,
        description: councilDescription,
        type: councilType,
        default_model: defaultModel,
        personas: councilType === "persona" ? personas : [],
        rubric,
      };
      if (councilType === "model" && councilModels.length > 0) {
        data.models = councilModels;
      }
      await api.updateCouncil(selectedCouncilId, data);
      setDirty(false);
      setStatus({ type: "success", message: `Council "${councilName}" saved` });
      const councilsList = await api.listCouncils();
      setCouncilList(councilsList);
      if (onConfigChanged) onConfigChanged();
    } catch (err) {
      setStatus({ type: "error", message: err.message });
    }
    setSaving(false);
  };

  const handleCreateCouncil = async () => {
    if (!newCouncilId || !newCouncilName) return;
    setSaving(true);
    try {
      const data = {
        id: newCouncilId,
        name: newCouncilName,
        description: "",
        type: newCouncilType,
        rubric: [
          { name: "Quality", weight: 3, description: "Overall quality of response" },
          { name: "Clarity", weight: 2, description: "How clear is the response?" },
        ],
      };

      if (newCouncilType === "persona") {
        data.personas = models.map((m) => ({
          model: m.id,
          role: "Advisor",
          prompt: "You are a knowledgeable advisor. Provide thoughtful analysis.",
        }));
      }

      await api.createCouncil(data);
      setShowNewCouncil(false);
      setNewCouncilId("");
      setNewCouncilName("");
      setNewCouncilType("persona");
      const councilsList = await api.listCouncils();
      setCouncilList(councilsList);
      setSelectedCouncilId(newCouncilId);
      setStatus({ type: "success", message: `Council "${newCouncilName}" created` });
      if (onConfigChanged) onConfigChanged();
    } catch (err) {
      setStatus({ type: "error", message: err.message });
    }
    setSaving(false);
  };

  const handleDeleteCouncil = async () => {
    if (!selectedCouncilId) return;
    if (!window.confirm(`Delete council "${councilName}"? This cannot be undone.`)) return;
    setSaving(true);
    try {
      await api.deleteCouncil(selectedCouncilId);
      const councilsList = await api.listCouncils();
      setCouncilList(councilsList);
      if (councilsList.length > 0) {
        setSelectedCouncilId(councilsList[0].id);
      }
      setStatus({ type: "success", message: "Council deleted" });
      if (onConfigChanged) onConfigChanged();
    } catch (err) {
      setStatus({ type: "error", message: err.message });
    }
    setSaving(false);
  };

  // ========== Rubric Tab Handlers ==========

  const handleRubricChange = (index, field, value) => {
    const updated = [...rubric];
    if (field === "weight") {
      value = Math.min(5, Math.max(1, parseInt(value) || 1));
    }
    updated[index] = { ...updated[index], [field]: value };
    setRubric(updated);
    markDirty();
  };

  const handleAddRubric = () => {
    setRubric([...rubric, { name: "", weight: 2, description: "" }]);
    markDirty();
  };

  const handleRemoveRubric = (index) => {
    if (rubric.length <= 1) return;
    setRubric(rubric.filter((_, i) => i !== index));
    markDirty();
  };

  // ========== Import/Export Handlers ==========

  const handleExport = async () => {
    setSaving(true);
    try {
      const data = await api.exportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `llm-council-config-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus({ type: "success", message: "Configuration exported" });
    } catch (err) {
      setStatus({ type: "error", message: "Export failed: " + err.message });
    }
    setSaving(false);
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSaving(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);

      if (!data.version) {
        throw new Error("Invalid config file: missing version field");
      }

      const result = await api.importConfig(data);
      setStatus({
        type: "success",
        message: `Imported: ${result.models_updated ? "models updated" : ""}${result.councils_updated?.length ? `, ${result.councils_updated.length} councils updated` : ""}${result.errors?.length ? `, ${result.errors.length} errors` : ""}`,
      });

      // Reload everything
      await loadConfig();
      if (onConfigChanged) onConfigChanged();
    } catch (err) {
      setStatus({ type: "error", message: "Import failed: " + err.message });
    }
    setSaving(false);
    // Reset file input so the same file can be re-imported
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ========== Close with unsaved check ==========

  const handleClose = () => {
    if (dirty && !window.confirm("You have unsaved changes. Discard?")) return;
    onClose();
  };

  // ========== Render functions ==========

  const renderModelsTab = () => (
    <>
      <div className="settings-section">
        <h3>Council Models</h3>
        {models.map((model, i) => (
          <div key={i} className="model-row">
            <input
              className="settings-input model-id-input"
              value={model.id}
              onChange={(e) => handleModelChange(i, "id", e.target.value)}
              placeholder="provider/model-name"
            />
            <input
              className="settings-input"
              value={model.name}
              onChange={(e) => handleModelChange(i, "name", e.target.value)}
              placeholder="Display Name"
            />
            <button
              className="model-remove-btn"
              onClick={() => handleRemoveModel(i)}
              title="Remove model"
            >
              &times;
            </button>
          </div>
        ))}
        <button className="model-add-btn" onClick={handleAddModel}>
          + Add Model
        </button>
      </div>

      <div className="settings-section">
        <h3>Roles</h3>
        <div className="settings-row">
          <span className="settings-label">Chairman</span>
          <select
            className="settings-select"
            value={chairman}
            onChange={(e) => {
              setChairman(e.target.value);
              markDirty();
            }}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name || m.id}
              </option>
            ))}
          </select>
        </div>
        <div className="settings-row">
          <span className="settings-label">Title Model</span>
          <input
            className="settings-input"
            value={titleModel}
            onChange={(e) => {
              setTitleModel(e.target.value);
              markDirty();
            }}
            placeholder="e.g. google/gemini-2.5-flash"
          />
        </div>
      </div>

      <div className="settings-section">
        <h3>Deliberation</h3>
        <div className="settings-row">
          <span className="settings-label">Rounds</span>
          <input
            className="settings-input"
            type="number"
            min="1"
            max="5"
            value={deliberationRounds}
            onChange={(e) => {
              setDeliberationRounds(parseInt(e.target.value) || 2);
              markDirty();
            }}
            style={{ width: 80, flex: "none" }}
          />
        </div>
      </div>

      <button
        className="settings-save-btn"
        onClick={handleSaveModels}
        disabled={saving}
      >
        {saving ? "Saving..." : "Save Models Config"}
      </button>
    </>
  );

  const renderCouncilsTab = () => (
    <>
      <div className="council-selector-row">
        <select
          className="settings-select"
          value={selectedCouncilId}
          onChange={(e) => {
            if (dirty && !window.confirm("Discard unsaved changes?")) return;
            setDirty(false);
            setSelectedCouncilId(e.target.value);
          }}
        >
          {councilList.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.id})
            </option>
          ))}
        </select>
        <button
          className="council-action-btn council-new-btn"
          onClick={() => setShowNewCouncil(true)}
        >
          + New
        </button>
        <button
          className="council-action-btn council-delete-btn"
          onClick={handleDeleteCouncil}
        >
          Delete
        </button>
      </div>

      {showNewCouncil && (
        <div className="new-council-dialog">
          <h4>Create New Council</h4>
          <div className="settings-row">
            <span className="settings-label">ID</span>
            <input
              className="settings-input"
              value={newCouncilId}
              onChange={(e) =>
                setNewCouncilId(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))
              }
              placeholder="my-council"
            />
          </div>
          <div className="settings-row">
            <span className="settings-label">Name</span>
            <input
              className="settings-input"
              value={newCouncilName}
              onChange={(e) => setNewCouncilName(e.target.value)}
              placeholder="My Council"
            />
          </div>
          <div className="settings-row">
            <span className="settings-label">Mode</span>
            <select
              className="settings-select"
              value={newCouncilType}
              onChange={(e) => setNewCouncilType(e.target.value)}
            >
              <option value="persona">Persona (expert roles with system prompts)</option>
              <option value="model">Model (raw multi-model, no personas)</option>
            </select>
          </div>
          <div className="new-council-actions">
            <button
              className="new-council-create-btn"
              onClick={handleCreateCouncil}
              disabled={!newCouncilId || !newCouncilName || saving}
            >
              Create
            </button>
            <button
              className="new-council-cancel-btn"
              onClick={() => setShowNewCouncil(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="settings-section">
        <h3>Details</h3>
        <div className="settings-row">
          <span className="settings-label">Name</span>
          <input
            className="settings-input"
            value={councilName}
            onChange={(e) => {
              setCouncilName(e.target.value);
              markDirty();
            }}
          />
        </div>
        <div className="settings-row">
          <span className="settings-label">Description</span>
          <input
            className="settings-input"
            value={councilDescription}
            onChange={(e) => {
              setCouncilDescription(e.target.value);
              markDirty();
            }}
          />
        </div>
        <div className="settings-row">
          <span className="settings-label">Mode</span>
          <select
            className="settings-select"
            value={councilType}
            onChange={(e) => {
              setCouncilType(e.target.value);
              markDirty();
            }}
          >
            <option value="persona">Persona (expert roles with system prompts)</option>
            <option value="model">Model (raw multi-model, no personas)</option>
          </select>
        </div>
        {councilType === "persona" && (
          <div className="settings-row">
            <span className="settings-label">Default Model</span>
            <select
              className="settings-select"
              value={defaultModel}
              onChange={(e) => {
                setDefaultModel(e.target.value);
                markDirty();
              }}
            >
              <option value="">— None (each persona specifies model) —</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || m.id}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {councilType === "persona" && (
        <div className="settings-section">
          <h3>Personas</h3>
          {personas.map((persona, i) => (
            <div key={i} className="persona-card">
              <div className="persona-card-header">
                <select
                  className="settings-select persona-model-select"
                  value={persona.model || defaultModel || ""}
                  onChange={(e) => handlePersonaChange(i, "model", e.target.value)}
                  title={defaultModel && !persona.model ? `Using default: ${defaultModel}` : ""}
                >
                  {defaultModel && (
                    <option value="">Use default ({models.find(m => m.id === defaultModel)?.name || defaultModel})</option>
                  )}
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name || m.id}
                    </option>
                  ))}
                </select>
                <input
                  className="settings-input"
                  value={persona.role || ""}
                  onChange={(e) => handlePersonaChange(i, "role", e.target.value)}
                  placeholder="Role name"
                  style={{ flex: 1 }}
                />
                <button
                  className="model-remove-btn"
                  onClick={() => handleRemovePersona(i)}
                  title="Remove persona"
                >
                  &times;
                </button>
              </div>
              <textarea
                className="persona-textarea"
                value={persona.prompt || ""}
                onChange={(e) => handlePersonaChange(i, "prompt", e.target.value)}
                placeholder="System prompt for this persona..."
              />
            </div>
          ))}
          <button className="model-add-btn" onClick={handleAddPersona}>
            + Add Persona
          </button>
        </div>
      )}

      {councilType === "model" && (
        <div className="settings-section">
          <h3>Models</h3>
          <p className="settings-hint">
            Uses global models by default. No system prompts — diversity comes from model architecture differences.
          </p>
        </div>
      )}

      <button
        className="settings-save-btn"
        onClick={handleSaveCouncil}
        disabled={saving}
      >
        {saving ? "Saving..." : "Save Council"}
      </button>
    </>
  );

  const renderRubricsTab = () => (
    <>
      <div className="council-selector-row">
        <select
          className="settings-select"
          value={selectedCouncilId}
          onChange={(e) => {
            if (dirty && !window.confirm("Discard unsaved changes?")) return;
            setDirty(false);
            setSelectedCouncilId(e.target.value);
          }}
        >
          {councilList.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.id})
            </option>
          ))}
        </select>
      </div>

      <div className="settings-section">
        <h3>Scoring Criteria</h3>
        {rubric.map((criterion, i) => (
          <div key={i} className="rubric-card">
            <input
              className="settings-input"
              value={criterion.name || ""}
              onChange={(e) => handleRubricChange(i, "name", e.target.value)}
              placeholder="Criterion name"
            />
            <input
              className="settings-input rubric-weight"
              type="number"
              min="1"
              max="5"
              value={criterion.weight || 2}
              onChange={(e) => handleRubricChange(i, "weight", e.target.value)}
              title="Weight (1-5)"
            />
            <input
              className="settings-input rubric-desc"
              value={criterion.description || ""}
              onChange={(e) => handleRubricChange(i, "description", e.target.value)}
              placeholder="Description"
            />
            <button
              className="model-remove-btn"
              onClick={() => handleRemoveRubric(i)}
              title="Remove criterion"
            >
              &times;
            </button>
          </div>
        ))}
        <button className="model-add-btn" onClick={handleAddRubric}>
          + Add Criterion
        </button>
      </div>

      <button
        className="settings-save-btn"
        onClick={handleSaveCouncil}
        disabled={saving}
      >
        {saving ? "Saving..." : "Save Rubric"}
      </button>
    </>
  );

  const renderImportExportTab = () => (
    <>
      <div className="settings-section">
        <h3>Export Configuration</h3>
        <p className="settings-hint">
          Download all models, councils, and rubric settings as a JSON file. Use this to back up your configuration or transfer it to another instance.
        </p>
        <button
          className="settings-save-btn export-btn"
          onClick={handleExport}
          disabled={saving}
        >
          {saving ? "Exporting..." : "Export Config"}
        </button>
      </div>

      <div className="settings-section">
        <h3>Import Configuration</h3>
        <p className="settings-hint">
          Upload a previously exported JSON file to restore or merge configuration. Existing settings will be overwritten by imported values.
        </p>
        <input
          type="file"
          accept=".json"
          ref={fileInputRef}
          onChange={handleImport}
          style={{ display: "none" }}
        />
        <button
          className="settings-save-btn import-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={saving}
        >
          {saving ? "Importing..." : "Import Config"}
        </button>
      </div>
    </>
  );

  return (
    <div className="settings-view">
      <div className="settings-header">
        <h2>Settings</h2>
        <button className="settings-close" onClick={handleClose}>
          &#x2715;
        </button>
      </div>

      <div className="settings-tabs">
        <button
          className={`settings-tab ${activeTab === "models" ? "active" : ""}`}
          onClick={() => setActiveTab("models")}
        >
          Models
        </button>
        <button
          className={`settings-tab ${activeTab === "councils" ? "active" : ""}`}
          onClick={() => setActiveTab("councils")}
        >
          Councils
        </button>
        <button
          className={`settings-tab ${activeTab === "rubrics" ? "active" : ""}`}
          onClick={() => setActiveTab("rubrics")}
        >
          Rubrics
        </button>
        <button
          className={`settings-tab ${activeTab === "importexport" ? "active" : ""}`}
          onClick={() => setActiveTab("importexport")}
        >
          Import/Export
        </button>
      </div>

      <div className="settings-content">
        {!configLoaded ? (
          <div className="leaderboard-loading">Loading configuration...</div>
        ) : activeTab === "models" ? (
          renderModelsTab()
        ) : activeTab === "councils" ? (
          renderCouncilsTab()
        ) : activeTab === "rubrics" ? (
          renderRubricsTab()
        ) : (
          renderImportExportTab()
        )}
      </div>

      {status.message && (
        <div className={`settings-status ${status.type}`}>
          <span>{status.message}</span>
        </div>
      )}
    </div>
  );
}

export default SettingsView;
