# Architecture Diagrams

## 1. Pipeline Overview

```mermaid
flowchart LR
    URLs["URL(s)"] --> A1

    subgraph A1["Agent 1: Downloader"]
        direction TB
        detect["Detect Source Type"] --> dl["Download Audio"]
        dl --> norm["Normalize to 16kHz mono WAV"]
        norm --> validate["Validate Duration"]
    end

    A1 -->|DownloadManifest| A2

    subgraph A2["Agent 2: Transcriber"]
        direction TB
        whisper["faster-whisper\n(large-v3)"] --> hall["Hallucination Check"]
        hall --> diar["Speaker Diarization\n(optional)"]
        diar --> vocab["Domain Vocabulary\nCorrections"]
        vocab --> llmpp["LLM Post-Processing\n(optional)"]
    end

    A2 -->|TranscriptOutput| A3

    subgraph A3["Agent 3: Enrichment"]
        direction TB
        refs["Identify References\n(Regex + LLM + MCP)"] --> verify["Batch Verify\nAgainst Vedabase"]
        verify --> gloss["Build Glossary\n& Thematic Index"]
        gloss --> enrich["LLM Enrichment\n(Chunked or Single-Pass)"]
    end

    A3 -->|EnrichedNotes| A3_5

    subgraph A3_5["Agent 3.5: Validator"]
        direction TB
        val["Validate Transcript\n& Enrichment Quality"]
    end

    A3_5 -->|ValidationReport| A4

    subgraph A4["Agent 4: Compiler"]
        direction TB
        chapters["Organize Chapters"] --> format["Format Markdown"]
        format --> indices["Build Verse Index\n& Glossary"]
        indices --> assemble["Assemble Book"]
    end

    A4 -->|BookOutput| PDF["PDF Generation\n(optional)"]

    style A1 fill:#e1f5fe,stroke:#0288d1
    style A2 fill:#f3e5f5,stroke:#7b1fa2
    style A3 fill:#fff3e0,stroke:#ef6c00
    style A3_5 fill:#fce4ec,stroke:#c62828
    style A4 fill:#e8f5e9,stroke:#2e7d32
```

## 2. Pipeline State Machine

```mermaid
stateDiagram-v2
    [*] --> PENDING

    PENDING --> DOWNLOADING
    DOWNLOADING --> DOWNLOADED
    DOWNLOADING --> FAILED

    DOWNLOADED --> TRANSCRIBING
    TRANSCRIBING --> TRANSCRIBED
    TRANSCRIBING --> FAILED

    TRANSCRIBED --> ENRICHING
    ENRICHING --> ENRICHED
    ENRICHING --> FAILED

    ENRICHED --> VALIDATING
    VALIDATING --> VALIDATED
    VALIDATING --> FAILED

    VALIDATED --> COMPILING
    COMPILING --> COMPILED
    COMPILING --> FAILED

    COMPILED --> PDF_GENERATING
    PDF_GENERATING --> PDF_GENERATED
    PDF_GENERATING --> FAILED

    PDF_GENERATED --> [*]
    COMPILED --> [*]

    note right of FAILED
        Any stage can fail.
        Pipeline continues with
        remaining successful URLs.
    end note
```

## 3. Enrichment Agent — Full Flow

```mermaid
flowchart TD
    input["TranscriptOutput"] --> step1

    subgraph step1["Step 1: Identify References"]
        direction TB
        regex["1a. Regex Pattern\nMatching"] --> merge1["Merge &\nDeduplicate"]
        llm_check{enable_llm?}
        llm_check -->|Yes| llm_id["1b. LLM Reference\nIdentification"]
        llm_check -->|No| merge1
        llm_id --> merge1
        mcp_check{HAS_MCP?}
        mcp_check -->|Yes| fuzzy["1c. MCP Batch\nFuzzy Match\n(unmatched slokas)"]
        mcp_check -->|No| merge1
        fuzzy --> merge1
    end

    step1 -->|"List[Reference]"| step2

    subgraph step2["Step 2: Batch Verify Against Vedabase"]
        direction TB
        split["Split BG vs Non-BG"] --> bg_path
        split --> other_path

        subgraph bg_path["BG References"]
            mcp_batch["MCP Batch Lookup\n(single session)"]
            mcp_batch --> bg_check{Verified?}
            bg_check -->|Yes| bg_verified["VerificationResult"]
            bg_check -->|No| bg_fallback["Add to\nVedabase Batch"]
        end

        subgraph other_path["Non-BG + Fallbacks"]
            veda_batch["Vedabase Batch Fetch\n(single cache load/save)"]
            veda_batch --> veda_check{Verified?}
            veda_check -->|Yes| veda_verified["VerificationResult"]
            veda_check -->|No| unverified["Unverified\nReference"]
        end
    end

    step2 --> step3["Step 3: Build Glossary"]
    step2 --> step4["Step 4: Build Thematic Index"]

    step3 --> step5
    step4 --> step5

    subgraph step5["Step 5: LLM Enrichment"]
        direction TB
        prep["Prepare Verified\nVerse Data"] --> prompt["Select Prompt\n(auto/lecture/verse-centric)"]
        prompt --> token_check{"estimated_tokens\n> 30k AND\nsegments > 20?"}
        token_check -->|Yes| chunked["Chunked Path\n(multiple LLM calls)"]
        token_check -->|No| single["Single-Pass Path\n(one LLM call)"]
    end

    step5 --> output["EnrichedNotes"]

    style step1 fill:#e3f2fd,stroke:#1565c0
    style step2 fill:#fff8e1,stroke:#f9a825
    style step5 fill:#fce4ec,stroke:#c62828
```

## 4. Batch Verification Strategy

```mermaid
flowchart TD
    refs["All Identified\nReferences"] --> split{"Split by\nScripture"}

    split -->|"scripture = BG"| bg_refs["BG References"]
    split -->|"scripture != BG"| other_refs["Non-BG References\n(SB, CC, NOI, etc.)"]

    bg_refs --> mcp_avail{HAS_MCP?}

    mcp_avail -->|Yes| mcp["MCP Batch Lookup\n(single session,\nall BG refs at once)"]
    mcp_avail -->|No| fallback_all["All BG refs\nto Vedabase batch"]

    mcp --> per_ref{Each ref\nverified?}
    per_ref -->|Yes| verified_mcp["Verified\n(status: verified)"]
    per_ref -->|No| fallback["Failed BG refs\nto Vedabase batch"]

    fallback --> combine["Combine:\nNon-BG + BG Fallbacks"]
    fallback_all --> combine
    other_refs --> combine

    combine --> veda["Vedabase Batch Fetch"]

    subgraph veda["batch_fetch_verses()"]
        direction TB
        cache_load["Load Cache Once"] --> pass1["Pass 1: Check Cache\n(separate hits vs misses)"]
        pass1 -->|Cache Hits| results["Results List"]
        pass1 -->|Cache Misses| pass2["Pass 2: Fetch from vedabase.io\n(sequential, rate-limited)"]
        pass2 --> results
        results --> cache_save["Save Cache Once"]
    end

    veda --> veda_check{Each ref\nverified?}
    veda_check -->|Yes| verified_veda["Verified\n(status: verified\nor cache_only)"]
    veda_check -->|No| unverified["Unverified\n(flagged for review)"]

    verified_mcp --> final["Final Output"]
    verified_veda --> final
    unverified --> final

    style mcp fill:#e8f5e9,stroke:#2e7d32
    style veda fill:#fff3e0,stroke:#ef6c00
    style verified_mcp fill:#c8e6c9,stroke:#388e3c
    style verified_veda fill:#c8e6c9,stroke:#388e3c
    style unverified fill:#ffcdd2,stroke:#d32f2f
```

## 5. Chunk with Purpose — Decision & Processing Flow

```mermaid
flowchart TD
    input["Transcript Text\n+ Verified Verses\n+ Segments"] --> estimate["Estimate Tokens\n(words x 1.3)"]

    estimate --> threshold{"tokens > 30,000\nAND segments > 20?"}

    threshold -->|No| single["Single-Pass Path"]
    threshold -->|Yes| chunk["Chunked Path"]

    subgraph single["Single-Pass LLM Enrichment"]
        direction TB
        ctx_s["Build Enrichment Context\n(group verses by scripture\nif 3+ from 2+ scriptures)"] --> call_s["Single Claude API Call"]
        call_s --> md_s["Enriched Markdown"]
    end

    subgraph chunk["Chunked LLM Enrichment"]
        direction TB
        find_breaks["Find Break Candidates"]
        find_breaks --> score["Score Breaks:\ngap_sec x 1.0\n+ speaker_change x 2.0\n+ ref_boundary x 1.5"]
        score --> select["Greedy Break Selection\n(chunks within 5k-40k tokens)"]
        select --> build["Build TranscriptChunks\n(assign refs & verses\nto each chunk)"]
        build --> loop["Process Each Chunk"]

        loop --> c1["Chunk 1\n(Claude API)"]
        loop --> c2["Chunk 2\n(Claude API)"]
        loop --> cn["Chunk N\n(Claude API)"]

        c1 --> merge["Merge Outputs"]
        c2 --> merge
        cn --> merge

        merge --> strip["Strip Duplicate Headers\n+ Insert Section Dividers"]
        strip --> md_c["Merged Enriched Markdown"]
    end

    single --> output["EnrichedNotes\n(same schema either path)"]
    chunk --> output

    style single fill:#e8f5e9,stroke:#2e7d32
    style chunk fill:#e3f2fd,stroke:#1565c0
```

## 6. Transcript Chunker Algorithm

```mermaid
flowchart TD
    input["Segments + Full Text\n+ References + Verified Verses"] --> est["Estimate Total Tokens"]

    est --> act{"tokens >\nactivation_threshold\n(30,000)?"}

    act -->|No| single_chunk["Return Single Chunk\n(backward compatible)"]

    act -->|Yes| find["Find Break Candidates"]

    subgraph find["Break Detection"]
        direction TB
        scan["Scan Adjacent\nSegment Pairs"] --> gap{"Temporal Gap\n>= 5 seconds?"}
        gap -->|Yes| gap_score["score += gap_sec x 1.0"]
        scan --> spk{"Speaker\nChange?"}
        spk -->|Yes| spk_score["score += 2.0"]
        scan --> ref{"Verse Reference\nBoundary?"}
        ref -->|Yes| ref_score["score += 1.5"]
    end

    find --> select["Select Breaks"]

    subgraph select["Greedy Break Selection"]
        direction TB
        sort["Sort Candidates\nby Score (desc)"] --> try["Try Adding Each\nCandidate"]
        try --> check{"All Chunks\n>= min_tokens\n(5,000)?"}
        check -->|Yes| keep["Keep Break"]
        check -->|No| skip["Skip Break"]
        keep --> oversized{"Any Chunk\n> max_tokens\n(40,000)?"}
        oversized -->|Yes| force["Force-Split\nat Midpoint"]
    end

    select --> build["Build Chunks"]

    subgraph build["Chunk Assembly"]
        direction TB
        ranges["Determine Segment\nRanges per Chunk"] --> assign_text["Join Segment Text\nper Chunk"]
        assign_text --> assign_refs["Assign References\nby segment_index"]
        assign_refs --> assign_verses["Assign Verified Verses\nby canonical_ref"]
        assign_verses --> themes["Tag Scripture Themes\n(BG, SB, CC, ...)"]
    end

    build --> output["List[TranscriptChunk]"]

    style find fill:#fff3e0,stroke:#ef6c00
    style select fill:#e3f2fd,stroke:#1565c0
    style build fill:#e8f5e9,stroke:#2e7d32
```

## 7. Enrichment Prompt Selection

```mermaid
flowchart TD
    verses["Verified Verse Data"] --> mode{"enrichment_mode?"}

    mode -->|"'auto'"| auto_check{"Verified\nverses <= 2?"}
    mode -->|"'lecture-centric'"| lecture["Lecture-Centric Prompt\n(v7.0)\nFocuses on speaker's\nteaching narrative"]
    mode -->|"'verse-centric'"| verse["Verse-Centric Prompt\n(v6.0)\nFocuses on scripture\nexposition & purports"]

    auto_check -->|Yes| lecture
    auto_check -->|No| verse

    lecture --> context["Build LLM Context"]
    verse --> context

    context --> group_check{"3+ verses from\n2+ scriptures?"}
    group_check -->|Yes| grouped["Group Verses by Scripture\n\nBhagavad-gita References\n  BG 2.47, BG 9.34\nSrimad-Bhagavatam References\n  SB 1.2.6, SB 3.25.21"]
    group_check -->|No| flat["Flat Chronological List\n\nBG 2.47\nBG 9.34"]

    grouped --> call["Claude API Call"]
    flat --> call

    style lecture fill:#e8f5e9,stroke:#2e7d32
    style verse fill:#e3f2fd,stroke:#1565c0
    style grouped fill:#fff3e0,stroke:#ef6c00
```

## 8. Multi-URL Pipeline Flow

```mermaid
flowchart TD
    urls["Multiple URLs"] --> dedup["Deduplicate URLs"]

    dedup --> phase1

    subgraph phase1["Phase 1: Download All"]
        direction LR
        d1["URL 1\nDownload"] --> d2["URL 2\nDownload"]
        d2 --> d3["URL N\nDownload"]
    end

    phase1 -->|"Filter failures"| phase2

    subgraph phase2["Phase 2: Transcribe All"]
        direction LR
        t1["Audio 1\nTranscribe"] --> t2["Audio 2\nTranscribe"]
        t2 --> t3["Audio N\nTranscribe"]
    end

    phase2 -->|"Filter failures"| phase3

    subgraph phase3["Phase 3: Enrich All"]
        direction LR
        e1["Transcript 1\nEnrich"] --> e2["Transcript 2\nEnrich"]
        e2 --> e3["Transcript N\nEnrich"]
    end

    phase3 -->|"Filter failures"| phase3_5

    subgraph phase3_5["Phase 3.5: Validate All"]
        direction LR
        v1["Enriched 1\nValidate"] --> v2["Enriched 2\nValidate"]
        v2 --> v3["Enriched N\nValidate"]
    end

    phase3_5 --> phase4

    subgraph phase4["Phase 4: Compile"]
        direction TB
        chapters["Organize into Chapters"] --> book["Assemble Single Book\nwith Indices & Glossary"]
    end

    phase4 --> phase5

    subgraph phase5["Phase 5: PDF (Optional)"]
        direction TB
        pdf["Generate PDF\nfrom Markdown"]
    end

    phase5 --> output["BookOutput + PDFOutput"]

    style phase1 fill:#e1f5fe,stroke:#0288d1
    style phase2 fill:#f3e5f5,stroke:#7b1fa2
    style phase3 fill:#fff3e0,stroke:#ef6c00
    style phase3_5 fill:#fce4ec,stroke:#c62828
    style phase4 fill:#e8f5e9,stroke:#2e7d32
    style phase5 fill:#efebe9,stroke:#4e342e
```

## 9. Vedabase URL Pattern Resolution

```mermaid
flowchart TD
    ref["Scripture Reference"] --> parse["Parse Scripture Type"]

    parse --> bg{"BG?"}
    parse --> sb{"SB?"}
    parse --> cc{"CC?"}
    parse --> noi{"NOI?"}
    parse --> iso{"ISO?"}

    bg -->|"BG 2.47"| bg_url["/en/library/bg/2/47/"]
    sb -->|"SB 1.2.6"| sb_url["/en/library/sb/1/2/6/"]
    cc -->|"CC Madhya 8.128"| cc_url["/en/library/cc/madhya/8/128/"]
    noi -->|"NOI 5"| noi_url["/en/library/noi/5/"]
    iso -->|"ISO 1"| iso_url["/en/library/iso/1/"]

    bg_url --> fetch["Fetch from vedabase.io"]
    sb_url --> fetch
    cc_url --> fetch
    noi_url --> fetch
    iso_url --> fetch

    fetch --> parse_html["Parse HTML:\nDevanagari, Verse Text,\nSynonyms, Translation,\nPurport Excerpt,\nCross-References"]

    parse_html --> cache["Store in JSON Cache"]
    cache --> result["Return Verified\nVerse Data"]

    style fetch fill:#fff3e0,stroke:#ef6c00
    style result fill:#c8e6c9,stroke:#388e3c
```
