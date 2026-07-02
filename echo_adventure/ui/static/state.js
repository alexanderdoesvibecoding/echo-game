"use strict";

// Client-side state is intentionally local. The server remains the source of
// truth for the run, decisions, and day advancement rules.
export const uiState = {
  state: null,
  welcomeModalVisible: false,
  newRunModalVisible: false,
  decisionModalVisible: false,
  decisionModalDismissedKey: null,
  settingsMenuOpen: false,
  runCycleId: 0,
  dayCycleKey: null,
  dayCycleProgress: 0,
  dayCycleTimer: null,
  dayCycleLastTick: null,
  dayCycleAdvancing: false,
  dayCycleShiftInFlight: false,
  dayCycleCompletedShiftMarkers: new Set(),
  dayDecisionThresholdKey: null,
  dayDecisionThresholds: [],
  pendingAdvanceState: null,
  modalVisible: false,
  pendingChoice: null,
};
