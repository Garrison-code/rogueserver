package defs

import (
	"bytes"
	"encoding/gob"
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func TestImportHistoryRoundTrip(t *testing.T) {
	original := SystemSaveData{TrainerId: 123, ImportHistory: &ImportHistory{Version: 1, Fingerprints: []string{strings.Repeat("a", 64), strings.Repeat("b", 64)}}}
	t.Run("JSON used by API and S3", func(t *testing.T) {
		encoded, err := json.Marshal(original)
		if err != nil {
			t.Fatal(err)
		}
		var decoded SystemSaveData
		if err := json.Unmarshal(encoded, &decoded); err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(decoded.ImportHistory, original.ImportHistory) {
			t.Fatalf("history lost: %#v", decoded.ImportHistory)
		}
	})
	t.Run("gob used by database", func(t *testing.T) {
		var buf bytes.Buffer
		if err := gob.NewEncoder(&buf).Encode(original); err != nil {
			t.Fatal(err)
		}
		var decoded SystemSaveData
		if err := gob.NewDecoder(&buf).Decode(&decoded); err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(decoded.ImportHistory, original.ImportHistory) {
			t.Fatalf("history lost: %#v", decoded.ImportHistory)
		}
	})
	t.Run("legacy JSON", func(t *testing.T) {
		var decoded SystemSaveData
		if err := json.Unmarshal([]byte(`{"trainerId":123}`), &decoded); err != nil {
			t.Fatal(err)
		}
		if decoded.ImportHistory != nil {
			t.Fatal("legacy save should have no history")
		}
	})
	t.Run("legacy gob", func(t *testing.T) {
		var buf bytes.Buffer
		old := struct{ TrainerId int }{123}
		if err := gob.NewEncoder(&buf).Encode(old); err != nil {
			t.Fatal(err)
		}
		var decoded SystemSaveData
		if err := gob.NewDecoder(&buf).Decode(&decoded); err != nil {
			t.Fatal(err)
		}
		if decoded.TrainerId != 123 || decoded.ImportHistory != nil {
			t.Fatal("legacy save changed")
		}
	})
}
