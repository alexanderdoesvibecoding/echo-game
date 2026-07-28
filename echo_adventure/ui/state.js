/** Single shared browser-state object used by all UI renderers. */

"use strict";

export const uiState = {
  // Authoritative server snapshot.
  state: null,
  // Browser-local overlays and preferences.
  welcomeModalVisible: false,
  tutorialStep: -1,
  tutorialCompletedRunKey: null,
  newRunModalVisible: false,
  newRunLoading: false,
  settingsMenuOpen: false,
  runCycleId: 0,
  // Animated day-cycle cursor and pending transition state.
  dayCycleKey: null,
  dayCycleProgress: 0,
  dayCycleTimer: null,
  dayCycleLastTick: null,
  dayCycleAdvancing: false,
  advanceRequestInFlight: false,
  dayDecisionThresholds: [],
  pendingAdvanceState: null,
  modalVisible: false,
  summaryAnimationKey: null,
  // Decision selection and request serialization.
  pendingChoice: null,
  choiceRequestInFlight: false,
  // Developer-only display preferences and mutation latch.
  devPanelCollapsed: false,
  devInstantProgression: false,
  devShowDiagnostics: false,
  devStrategy: "echo",
  devRequestInFlight: false,
  devSeededRun: false,
};
