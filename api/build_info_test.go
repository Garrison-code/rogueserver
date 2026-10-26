// SPDX-FileCopyrightText: 2026 Garrison-code
// SPDX-License-Identifier: AGPL-3.0-or-later
package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGameBuildInfo(t *testing.T) {
	originalRevision, originalID := BuildRevision, BuildID
	t.Cleanup(func() { BuildRevision, BuildID = originalRevision, originalID })
	BuildRevision, BuildID = "0123456789012345678901234567890123456789", "1234-2"
	response := httptest.NewRecorder()
	handleGameBuildInfo(response, httptest.NewRequest(http.MethodGet, "/game/build-info", nil))
	if response.Code != http.StatusOK || response.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("build information must be readable and never cached")
	}
	var value map[string]string
	if err := json.Unmarshal(response.Body.Bytes(), &value); err != nil {
		t.Fatal(err)
	}
	if value["revision"] != BuildRevision || value["build_id"] != BuildID || len(value) != 2 {
		t.Fatal("build identity missing or unexpected information exposed")
	}
}
