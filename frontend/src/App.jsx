import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import ChatInterface from "./components/ChatInterface";
import CouncilSelector from "./components/CouncilSelector";
import PanelSelector from "./components/PanelSelector";
import LeaderboardView from "./components/LeaderboardView";
import SettingsView from "./components/SettingsView";
import { api } from "./api";
import "./App.css";

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [initError, setInitError] = useState(null);

  // Council state
  const [councils, setCouncils] = useState([]);
  const [selectedCouncil, setSelectedCouncil] = useState("personal");
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // Panel selection state
  const [pendingMessage, setPendingMessage] = useState(null);
  const [suggestedPanel, setSuggestedPanel] = useState(null);
  const [availableAdvisors, setAvailableAdvisors] = useState([]);
  const [availableModels, setAvailableModels] = useState([]);
  const [isRouting, setIsRouting] = useState(false);
  const [autoAcceptPanel, setAutoAcceptPanel] = useState(
    () => localStorage.getItem("autoAcceptPanel") === "true"
  );

  useEffect(() => {
    const init = async () => {
      try {
        setInitError(null);
        const [councilsList, convs] = await Promise.all([
          api.listCouncils().catch(() => []),
          loadConversations(true),
        ]);
        if (councilsList.length > 0) {
          setCouncils(councilsList);
          setSelectedCouncil(councilsList[0].id);
        }

        const lastId = localStorage.getItem("lastConversationId");
        if (lastId && convs?.some((c) => c.id === lastId)) {
          await selectConversation(lastId);
        }
      } catch (err) {
        console.error("Init error:", err);
        setInitError(err.message);
      } finally {
        setIsInitializing(false);
      }
    };
    init();
  }, []);

  // Persist auto-accept preference
  useEffect(() => {
    localStorage.setItem("autoAcceptPanel", autoAcceptPanel.toString());
  }, [autoAcceptPanel]);

  const loadConversations = async (throwOnError = false) => {
    try {
      const convs = await api.listConversations();
      const active = convs.filter((c) => !c.deleted);
      setConversations(active);
      return active;
    } catch (err) {
      console.error("Failed to load conversations:", err);
      if (throwOnError) throw err;
      return [];
    }
  };

  const selectConversation = async (conversationId) => {
    try {
      const conv = await api.getConversation(conversationId);
      setCurrentConversationId(conversationId);
      setCurrentConversation(conv);
      if (conv.council_id && conv.council_id !== selectedCouncil) {
        setSelectedCouncil(conv.council_id);
      }
      localStorage.setItem("lastConversationId", conversationId);
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  };

  const createNewConversation = async () => {
    try {
      const conv = await api.createConversation(selectedCouncil);
      setCurrentConversationId(conv.id);
      setCurrentConversation(conv);
      localStorage.setItem("lastConversationId", conv.id);
      await loadConversations();
      return conv;
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  };

  const deleteConversation = async (conversationId) => {
    try {
      await api.deleteConversation(conversationId, selectedCouncil);
      if (currentConversationId === conversationId) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
      await loadConversations();
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  const currentCouncil = councils.find((c) => c.id === selectedCouncil);
  const isV2Council = currentCouncil?.version === 2 || currentCouncil?.type === "advisor";

  const handleSendMessage = async (content) => {
    if (!content.trim()) return;

    // For v2 councils with auto-accept OFF, route first then show panel
    if (isV2Council && !autoAcceptPanel) {
      setPendingMessage(content);
      setIsRouting(true);
      try {
        const routeResult = await api.routeQuestion(selectedCouncil, content);
        setSuggestedPanel(routeResult.panel);
        setAvailableAdvisors(routeResult.available_advisors || []);
        setAvailableModels(routeResult.models || []);
      } catch (err) {
        console.error("Routing failed, sending without panel:", err);
        // Fall through to send without panel
        await sendWithPanel(content, null);
      } finally {
        setIsRouting(false);
      }
      return;
    }

    // Auto-accept or v1 council: send directly (backend will route internally)
    await sendWithPanel(content, null);
  };

  const handlePanelConfirm = async (panel) => {
    const content = pendingMessage;
    setPendingMessage(null);
    setSuggestedPanel(null);
    setAvailableAdvisors([]);
    setAvailableModels([]);
    await sendWithPanel(content, panel);
  };

  const handlePanelCancel = () => {
    setPendingMessage(null);
    setSuggestedPanel(null);
    setAvailableAdvisors([]);
    setAvailableModels([]);
  };

  const handleSendDirect = async (content) => {
    if (!content.trim()) return;
    await sendWithPanel(content, null, true);
  };

  const sendWithPanel = async (content, panelOverride, forceDirect = false) => {
    let convId = currentConversationId;
    if (!convId) {
      const conv = await createNewConversation();
      if (!conv) return;
      convId = conv.id;
    }

    setIsLoading(true);

    // Add user message to local state
    setCurrentConversation((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: [...prev.messages, { role: "user", content }],
      };
    });

    // Create placeholder for assistant response
    const assistantMsg = {
      role: "assistant",
      stage1: [],
      stage2: [],
      stage3: {},
      analysis: null,
      panel: null,
    };
    setCurrentConversation((prev) => ({
      ...prev,
      messages: [...prev.messages, assistantMsg],
    }));

    try {
      await api.sendMessageStreamTokens(
        convId,
        content,
        (eventType, data) => {
          setCurrentConversation((prev) => {
            if (!prev) return prev;
            const messages = [...prev.messages];
            const lastMsg = { ...messages[messages.length - 1] };

            switch (eventType) {
              case "routing_complete":
              case "panel_confirmed":
                lastMsg.panel = data.panel;
                break;

              case "stage1_model_complete":
                lastMsg.stage1 = [
                  ...(lastMsg.stage1 || []),
                  {
                    model: data.model,
                    role: data.role,
                    member_id: data.member_id,
                    response: data.response,
                  },
                ];
                break;

              case "stage2_model_complete":
                lastMsg.stage2 = [
                  ...(lastMsg.stage2 || []),
                  {
                    model: data.model,
                    role: data.role,
                    member_id: data.member_id,
                    ranking: data.ranking,
                  },
                ];
                break;

              case "analysis":
                lastMsg.analysis = data;
                break;

              case "stage3_complete":
                lastMsg.stage3 = {
                  model: data.model,
                  response: data.response,
                };
                break;

              case "classification_complete":
                lastMsg.classification = { type: data.type, reasoning: data.reasoning };
                if (data.type === "direct" || data.type === "followup" || data.type === "chat" || data.type === "factual") {
                  lastMsg.responseType = "direct";
                }
                break;

              case "direct_start":
                lastMsg.responseType = "direct";
                break;

              case "usage_update":
                lastMsg.usage = {
                  ...(lastMsg.usage || {}),
                  by_stage: {
                    ...(lastMsg.usage?.by_stage || {}),
                    [data.stage]: data.usage,
                  },
                  total: data.running_total,
                  running_total: data.running_total,
                };
                break;

              case "done":
                if (data.usage) {
                  lastMsg.usage = data.usage;
                }
                break;

              case "error":
                lastMsg.stage3 = {
                  model: "error",
                  response: `Error: ${data.message || "Unknown error"}`,
                };
                break;
            }

            messages[messages.length - 1] = lastMsg;
            return { ...prev, messages };
          });
        },
        selectedCouncil,
        panelOverride,
        forceDirect
      );

      setTimeout(async () => {
        try {
          const conv = await api.getConversation(convId);
          setCurrentConversation(conv);
          await loadConversations();
        } catch (e) {
          console.warn("Failed to reload conversation:", e);
        }
      }, 1000);
    } catch (err) {
      console.error("Message send error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfigChanged = async () => {
    try {
      const councilsList = await api.listCouncils();
      setCouncils(councilsList);
    } catch (err) {
      console.error("Failed to reload councils:", err);
    }
  };

  if (showSettings) {
    return (
      <SettingsView
        councils={councils}
        onClose={() => setShowSettings(false)}
        onConfigChanged={handleConfigChanged}
      />
    );
  }

  if (showLeaderboard) {
    return (
      <LeaderboardView
        councils={councils}
        onClose={() => setShowLeaderboard(false)}
      />
    );
  }

  if (isInitializing) {
    return (
      <div className="app-loading">
        <div className="loading-spinner" />
        <p>Connecting to LLM Council...</p>
      </div>
    );
  }

  if (initError) {
    return (
      <div className="app-error">
        <h2>Connection Error</h2>
        <p>{initError}</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={selectConversation}
        onNewConversation={createNewConversation}
        onDeleteConversation={deleteConversation}
        councilSelector={
          <CouncilSelector
            councils={councils}
            selectedCouncil={selectedCouncil}
            onSelectCouncil={setSelectedCouncil}
            isLoading={isLoading}
          />
        }
        onShowLeaderboard={() => setShowLeaderboard(true)}
        onShowSettings={() => setShowSettings(true)}
      />
      <div className="main-content">
        {suggestedPanel && (
          <PanelSelector
            panel={suggestedPanel}
            availableAdvisors={availableAdvisors}
            availableModels={availableModels}
            question={pendingMessage}
            onConfirm={handlePanelConfirm}
            onCancel={handlePanelCancel}
            autoAccept={autoAcceptPanel}
            onAutoAcceptChange={setAutoAcceptPanel}
          />
        )}
        <ChatInterface
          conversation={currentConversation}
          onSendMessage={handleSendMessage}
          onSendDirect={handleSendDirect}
          isLoading={isLoading || isRouting}
          councilName={currentCouncil?.name || "Council"}
          isRouting={isRouting}
        />
      </div>
    </div>
  );
}

export default App;
