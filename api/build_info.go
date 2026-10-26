// SPDX-FileCopyrightText: 2026 Garrison-code
// SPDX-License-Identifier: AGPL-3.0-or-later
package api

import "net/http"

// BuildRevision and BuildID are public build metadata injected with -ldflags.
var BuildRevision = "unknown"
var BuildID = "unknown"

func handleGameBuildInfo(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, r, struct {
		Revision string `json:"revision"`
		BuildID  string `json:"build_id"`
	}{Revision: BuildRevision, BuildID: BuildID})
}
