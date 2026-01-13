"""Comprehensive CLI test suite for the agent.

Tests:
- All tools individually
- Multiple tools together
- Hallucination detection
- Source citation accuracy
- URL correctness
- Tool selection logic
- Language handling
- Edge cases
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Register all tools BEFORE importing the agent
from src.mcp.registry import get_registry
from src.tools.wikipedia.tools import register_tools as register_wikipedia
from src.tools.snl.tools import register_tools as register_snl
from src.tools.riksantikvaren_ogc.tools import register_tools as register_ogc
from src.tools.riksantikvaren_arcgis.tools import register_tools as register_arcgis
from src.tools.example.tools import register_tools as register_example

registry = get_registry()
register_example(registry)
register_wikipedia(registry)
register_snl(registry)
register_ogc(registry)
register_arcgis(registry)

print(f"Registered {len(registry.list_tools())} tools")

from src.agent.runner import AgentRunner, ChatRequest

# Test questions organized by category and difficulty
TEST_QUESTIONS = [
    # ==========================================================================
    # CATEGORY 1: Single Tool Tests - Wikipedia
    # ==========================================================================
    {
        "id": "wiki-1",
        "category": "Wikipedia - Easy",
        "question": "What is the Eiffel Tower?",
        "sources": ["wikipedia"],
        "expected_tools": ["wikipedia-"],
        "notes": "Basic Wikipedia lookup, should get clear answer"
    },
    {
        "id": "wiki-2", 
        "category": "Wikipedia - Medium",
        "question": "Tell me about Edvard Munch and his most famous painting",
        "sources": ["wikipedia"],
        "expected_tools": ["wikipedia-"],
        "notes": "Should find The Scream, test Norwegian artist knowledge"
    },
    {
        "id": "wiki-3",
        "category": "Wikipedia - Geosearch",
        "question": "What interesting places are near coordinates 59.9139, 10.7522 (Oslo)?",
        "sources": ["wikipedia"],
        "expected_tools": ["wikipedia-geosearch"],
        "notes": "Should use geosearch tool"
    },
    
    # ==========================================================================
    # CATEGORY 2: Single Tool Tests - SNL
    # ==========================================================================
    {
        "id": "snl-1",
        "category": "SNL - Easy",
        "question": "Hva er Bryggen i Bergen?",
        "sources": ["snl"],
        "expected_tools": ["snl-"],
        "notes": "Basic SNL lookup in Norwegian"
    },
    {
        "id": "snl-2",
        "category": "SNL - Medium",
        "question": "Fortell meg om vikingskipene som er funnet i Norge",
        "sources": ["snl"],
        "expected_tools": ["snl-"],
        "notes": "Should find Oseberg, Gokstad, Tune ships"
    },
    {
        "id": "snl-3",
        "category": "SNL - Hard",
        "question": "Hva er stavkirker og hvor mange finnes i Norge?",
        "sources": ["snl"],
        "expected_tools": ["snl-"],
        "notes": "Should find accurate count (~28 remaining)"
    },
    
    # ==========================================================================
    # CATEGORY 3: Single Tool Tests - Riksantikvaren (ArcGIS)
    # ==========================================================================
    {
        "id": "arcgis-1",
        "category": "ArcGIS - Easy",
        "question": "Find cultural heritage sites near Oslo city center (59.9139, 10.7522)",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-nearby"],
        "notes": "Should use arcgis-nearby, return Oslo sites with distances"
    },
    {
        "id": "arcgis-2",
        "category": "ArcGIS - Medium",
        "question": "What protected buildings are near Akershus Festning?",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-"],
        "notes": "Should find fortress and nearby protected buildings"
    },
    {
        "id": "arcgis-3",
        "category": "ArcGIS - Hard",
        "question": "Find Viking age cultural heritage sites near Tønsberg (59.2675, 10.4076)",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-nearby"],
        "notes": "Tønsberg is one of Norway's oldest cities, should find relevant sites"
    },
    
    # ==========================================================================
    # CATEGORY 4: Single Tool Tests - Riksantikvaren (OGC/Brukerminner)
    # ==========================================================================
    {
        "id": "ogc-1",
        "category": "OGC/Brukerminner - Easy",
        "question": "Are there any user memories (brukerminner) near Oslo?",
        "sources": ["riksantikvaren"],
        "expected_tools": ["riksantikvaren-nearby"],
        "notes": "Should use riksantikvaren-nearby with brukerminner dataset"
    },
    {
        "id": "ogc-2",
        "category": "OGC/Brukerminner - Medium",
        "question": "Find personal stories about places in Bergen (60.3913, 5.3221)",
        "sources": ["riksantikvaren"],
        "expected_tools": ["riksantikvaren-nearby"],
        "notes": "Should search brukerminner with larger radius"
    },
    
    # ==========================================================================
    # CATEGORY 5: Multi-Tool Tests
    # ==========================================================================
    {
        "id": "multi-1",
        "category": "Multi-tool - Easy",
        "question": "Tell me about Nidarosdomen",
        "sources": ["wikipedia", "snl"],
        "expected_tools": ["wikipedia-", "snl-"],
        "notes": "Should use both Wikipedia and SNL for comprehensive answer"
    },
    {
        "id": "multi-2",
        "category": "Multi-tool - Medium",
        "question": "What is Akershus Festning and what cultural heritage sites are nearby?",
        "sources": ["snl", "riksantikvaren"],
        "expected_tools": ["snl-", "arcgis-"],
        "notes": "Should combine encyclopedia info with spatial search"
    },
    {
        "id": "multi-3",
        "category": "Multi-tool - Hard",
        "question": "Compare the historical significance of Bryggen in Bergen with the Hanseatic League history from Wikipedia",
        "sources": ["wikipedia", "snl", "riksantikvaren"],
        "expected_tools": ["wikipedia-", "snl-", "arcgis-"],
        "notes": "Complex query requiring multiple sources and synthesis"
    },
    {
        "id": "multi-4",
        "category": "Multi-tool - Comprehensive",
        "question": "I'm visiting Trondheim. Tell me about Nidarosdomen, find nearby cultural heritage sites, and any user memories about the area.",
        "sources": ["wikipedia", "snl", "riksantikvaren"],
        "expected_tools": ["snl-", "arcgis-nearby", "riksantikvaren-nearby"],
        "notes": "Should use all three sources comprehensively"
    },
    
    # ==========================================================================
    # CATEGORY 6: Language Tests
    # ==========================================================================
    {
        "id": "lang-1",
        "category": "Language - Norwegian question",
        "question": "Hva vet du om Holmenkollen?",
        "sources": ["wikipedia", "snl"],
        "expected_tools": ["snl-", "wikipedia-"],
        "notes": "Norwegian question should get Norwegian response"
    },
    {
        "id": "lang-2",
        "category": "Language - English question",
        "question": "What do you know about the Viking Ship Museum in Oslo?",
        "sources": ["wikipedia", "snl"],
        "expected_tools": ["snl-", "wikipedia-"],
        "notes": "English question should get English response even from Norwegian sources"
    },
    {
        "id": "lang-3",
        "category": "Language - Mixed",
        "question": "Tell me about Vigelandsparken using Norwegian sources",
        "sources": ["snl"],
        "expected_tools": ["snl-"],
        "notes": "English question, Norwegian source, should respond in English"
    },
    
    # ==========================================================================
    # CATEGORY 7: Hallucination Tests
    # ==========================================================================
    {
        "id": "halluc-1",
        "category": "Hallucination - Non-existent place",
        "question": "Tell me about the ancient Viking fortress of Nordfjellheim",
        "sources": ["wikipedia", "snl", "riksantikvaren"],
        "expected_tools": [],
        "notes": "FAKE PLACE - should admit it can't find information"
    },
    {
        "id": "halluc-2",
        "category": "Hallucination - Real place, wrong facts",
        "question": "Is it true that Akershus Festning was built by the Romans?",
        "sources": ["snl", "riksantikvaren"],
        "expected_tools": ["snl-"],
        "notes": "FALSE claim - should correct this (built by Håkon V around 1299)"
    },
    {
        "id": "halluc-3",
        "category": "Hallucination - Obscure request",
        "question": "What color was the original paint on Urnes stave church in the year 1150?",
        "sources": ["wikipedia", "snl"],
        "expected_tools": ["snl-", "wikipedia-"],
        "notes": "Very specific - should admit uncertainty if data not available"
    },
    
    # ==========================================================================
    # CATEGORY 8: Edge Cases
    # ==========================================================================
    {
        "id": "edge-1",
        "category": "Edge - Empty result handling",
        "question": "Find cultural heritage sites in the middle of the Atlantic Ocean (45.0, -30.0)",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-nearby"],
        "notes": "Should handle no results gracefully"
    },
    {
        "id": "edge-2",
        "category": "Edge - Ambiguous query",
        "question": "Tell me about the church",
        "sources": ["wikipedia", "snl"],
        "expected_tools": ["snl-", "wikipedia-"],
        "notes": "Vague query - should ask for clarification or pick notable examples"
    },
    {
        "id": "edge-3",
        "category": "Edge - Very long query",
        "question": "I am a tourist visiting Norway for the first time and I want to learn about the history of Oslo, specifically the medieval period, the Viking heritage, the royal palace, and any interesting cultural heritage sites near the city center that I should visit, preferably with links to official sources",
        "sources": ["wikipedia", "snl", "riksantikvaren"],
        "expected_tools": ["snl-", "wikipedia-", "arcgis-nearby"],
        "notes": "Long query - should handle comprehensively"
    },
    
    # ==========================================================================
    # CATEGORY 9: Tool Selection Tests
    # ==========================================================================
    {
        "id": "select-1",
        "category": "Tool Selection - Should prefer ArcGIS",
        "question": "What official cultural heritage sites are within 500 meters of the Royal Palace in Oslo?",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-nearby"],
        "notes": "Should use arcgis-nearby (official sites), not riksantikvaren-nearby"
    },
    {
        "id": "select-2",
        "category": "Tool Selection - Should prefer Brukerminner",
        "question": "Are there any personal stories or user memories about Grünerløkka in Oslo?",
        "sources": ["riksantikvaren"],
        "expected_tools": ["riksantikvaren-nearby"],
        "notes": "Should use riksantikvaren-nearby (brukerminner), not arcgis"
    },
    {
        "id": "select-3",
        "category": "Tool Selection - Should use both Riksantikvaren tools",
        "question": "Find both official heritage sites AND user memories near Stavanger",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-nearby", "riksantikvaren-nearby"],
        "notes": "Should use BOTH tools"
    },
    
    # ==========================================================================
    # CATEGORY 10: Source Attribution Tests
    # ==========================================================================
    {
        "id": "source-1",
        "category": "Sources - Should cite SNL",
        "question": "Hva er Geiranger og hvorfor er det et verdensarvsted?",
        "sources": ["snl"],
        "expected_tools": ["snl-"],
        "notes": "Should include SNL source in response"
    },
    {
        "id": "source-2",
        "category": "Sources - Should cite Kulturminnesøk",
        "question": "Find protected buildings near Bergen city center",
        "sources": ["riksantikvaren"],
        "expected_tools": ["arcgis-nearby"],
        "notes": "Should include kulturminnesok.no links"
    },
    {
        "id": "source-3",
        "category": "Sources - Multiple sources",
        "question": "Tell me about Røros, the UNESCO world heritage mining town",
        "sources": ["wikipedia", "snl", "riksantikvaren"],
        "expected_tools": ["snl-", "wikipedia-", "arcgis-nearby"],
        "notes": "Should cite multiple sources used in the answer"
    },
]


async def run_test(runner: AgentRunner, test: dict, log_file) -> dict:
    """Run a single test and return results."""
    print(f"\n{'='*70}")
    print(f"TEST: {test['id']} - {test['category']}")
    print(f"{'='*70}")
    print(f"Question: {test['question']}")
    print(f"Sources: {test['sources']}")
    print(f"Expected tools: {test['expected_tools']}")
    print("-" * 70)
    
    request = ChatRequest(
        message=test["question"],
        sources=test["sources"],
        conversation_history=[]
    )
    
    result = {
        "id": test["id"],
        "category": test["category"],
        "question": test["question"],
        "sources_enabled": test["sources"],
        "expected_tools": test["expected_tools"],
        "notes": test["notes"],
        "tools_used": [],
        "tools_details": [],
        "response_text": "",
        "sources_cited": [],
        "processing_time_ms": 0,
        "errors": [],
        "passed": False,
        "reflections": []
    }
    
    try:
        async for event in runner.chat_stream(request):
            event_type = type(event).__name__
            
            if event_type == "StatusEvent":
                print(f"📊 {event.message}")
            elif event_type == "ToolStartEvent":
                print(f"🔧 Tool: {event.tool}")
                result["tools_used"].append(event.tool)
                result["tools_details"].append({
                    "tool": event.tool,
                    "arguments": event.arguments
                })
            elif event_type == "ToolEndEvent":
                status = "✅" if event.success else "❌"
                print(f"{status} {event.tool} complete")
            elif event_type == "TokenEvent":
                pass  # Don't print tokens
            elif event_type == "DoneEvent":
                result["response_text"] = event.response.response.text
                result["sources_cited"] = [
                    {"title": s.title, "url": s.url, "provider": s.provider}
                    for s in event.response.sources
                ]
                result["processing_time_ms"] = event.response.metadata.processing_time_ms
                print(f"\n📝 Response ({len(result['response_text'])} chars, {result['processing_time_ms']}ms)")
            elif event_type == "ErrorEvent":
                result["errors"].append(event.message)
                print(f"❌ Error: {event.message}")
        
        # Evaluate results
        result["reflections"] = evaluate_test(test, result)
        result["passed"] = len([r for r in result["reflections"] if r.startswith("❌")]) == 0
        
    except Exception as e:
        result["errors"].append(str(e))
        result["reflections"].append(f"❌ Exception: {str(e)}")
        print(f"❌ Exception: {e}")
    
    # Log to file
    log_test_result(log_file, result)
    
    return result


def evaluate_test(test: dict, result: dict) -> list[str]:
    """Evaluate test results and return reflections."""
    reflections = []
    
    # Check if expected tools were used
    for expected in test["expected_tools"]:
        found = any(expected in tool for tool in result["tools_used"])
        if found:
            reflections.append(f"✅ Used expected tool pattern: {expected}")
        else:
            reflections.append(f"❌ Missing expected tool pattern: {expected}")
    
    # Check if response was generated
    if result["response_text"]:
        reflections.append(f"✅ Response generated ({len(result['response_text'])} chars)")
    else:
        reflections.append("❌ No response generated")
    
    # Check for errors
    if result["errors"]:
        reflections.append(f"❌ Errors occurred: {result['errors']}")
    
    # Check sources
    if result["sources_cited"]:
        reflections.append(f"✅ Sources cited: {len(result['sources_cited'])}")
        # Check for valid URLs
        for source in result["sources_cited"]:
            if source["url"].startswith("http"):
                reflections.append(f"  ✅ Valid URL: {source['url'][:60]}...")
            else:
                reflections.append(f"  ❌ Invalid URL: {source['url']}")
    else:
        # Not always an error - some tests shouldn't find sources
        if "halluc" in test["id"] and "Non-existent" in test["category"]:
            reflections.append("✅ No sources (expected for fake place)")
        else:
            reflections.append("⚠️ No sources cited")
    
    # Check response language
    if "Norwegian question" in test["category"]:
        # Check for Norwegian words
        norwegian_indicators = ["er", "og", "det", "som", "med", "av"]
        has_norwegian = any(f" {word} " in result["response_text"].lower() for word in norwegian_indicators)
        if has_norwegian:
            reflections.append("✅ Response appears to be in Norwegian")
        else:
            reflections.append("⚠️ Response may not be in Norwegian")
    
    # Check processing time
    if result["processing_time_ms"] > 0:
        if result["processing_time_ms"] < 5000:
            reflections.append(f"✅ Fast response ({result['processing_time_ms']}ms)")
        elif result["processing_time_ms"] < 15000:
            reflections.append(f"⚠️ Moderate response time ({result['processing_time_ms']}ms)")
        else:
            reflections.append(f"❌ Slow response ({result['processing_time_ms']}ms)")
    
    return reflections


def log_test_result(log_file, result: dict):
    """Write test result to log file."""
    log_file.write(f"\n## Test: {result['id']} - {result['category']}\n\n")
    log_file.write(f"**Question:** {result['question']}\n\n")
    log_file.write(f"**Sources enabled:** {', '.join(result['sources_enabled'])}\n\n")
    log_file.write(f"**Expected tools:** {', '.join(result['expected_tools']) or 'None'}\n\n")
    log_file.write(f"**Test notes:** {result['notes']}\n\n")
    
    log_file.write("### Tools Used\n\n")
    if result["tools_details"]:
        for tool in result["tools_details"]:
            log_file.write(f"- `{tool['tool']}`: `{json.dumps(tool['arguments'], ensure_ascii=False)}`\n")
    else:
        log_file.write("- None\n")
    log_file.write("\n")
    
    log_file.write("### Response\n\n")
    log_file.write(f"**Processing time:** {result['processing_time_ms']}ms\n\n")
    if result["response_text"]:
        # Truncate very long responses
        text = result["response_text"]
        if len(text) > 2000:
            text = text[:2000] + "\n\n*[Response truncated for log]*"
        log_file.write(f"```markdown\n{text}\n```\n\n")
    else:
        log_file.write("*No response*\n\n")
    
    log_file.write("### Sources Cited\n\n")
    if result["sources_cited"]:
        for source in result["sources_cited"]:
            log_file.write(f"- [{source['title']}]({source['url']}) ({source['provider']})\n")
    else:
        log_file.write("- None\n")
    log_file.write("\n")
    
    log_file.write("### Evaluation\n\n")
    for reflection in result["reflections"]:
        log_file.write(f"- {reflection}\n")
    log_file.write("\n")
    
    status = "✅ PASSED" if result["passed"] else "❌ FAILED"
    log_file.write(f"**Status:** {status}\n\n")
    log_file.write("---\n")
    
    log_file.flush()


async def main():
    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set in environment")
        print("Please set it in .env file or export it")
        sys.exit(1)
    
    print("="*70)
    print("COMPREHENSIVE AGENT CLI TEST SUITE")
    print("="*70)
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Total tests: {len(TEST_QUESTIONS)}")
    print("="*70)
    
    # Create runner
    runner = AgentRunner(api_key)
    
    # Create log file
    log_path = Path(__file__).parent.parent / "artifacts" / "test_logs"
    log_path.mkdir(parents=True, exist_ok=True)
    log_filename = log_path / f"agent_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    results = []
    
    with open(log_filename, "w", encoding="utf-8") as log_file:
        # Write header
        log_file.write(f"# Agent CLI Test Results\n\n")
        log_file.write(f"**Date:** {datetime.now().isoformat()}\n\n")
        log_file.write(f"**Total tests:** {len(TEST_QUESTIONS)}\n\n")
        log_file.write("---\n")
        
        # Run all tests
        for i, test in enumerate(TEST_QUESTIONS):
            print(f"\n[{i+1}/{len(TEST_QUESTIONS)}]", end="")
            result = await run_test(runner, test, log_file)
            results.append(result)
        
        # Write summary
        passed = len([r for r in results if r["passed"]])
        failed = len(results) - passed
        
        log_file.write("\n# Summary\n\n")
        log_file.write(f"**Total:** {len(results)}\n\n")
        log_file.write(f"**Passed:** {passed}\n\n")
        log_file.write(f"**Failed:** {failed}\n\n")
        log_file.write(f"**Pass rate:** {100*passed/len(results):.1f}%\n\n")
        
        # Group by category
        log_file.write("## Results by Category\n\n")
        categories = {}
        for r in results:
            cat = r["category"].split(" - ")[0]
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if r["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1
        
        log_file.write("| Category | Passed | Failed | Rate |\n")
        log_file.write("|----------|--------|--------|------|\n")
        for cat, counts in categories.items():
            total = counts["passed"] + counts["failed"]
            rate = 100 * counts["passed"] / total
            log_file.write(f"| {cat} | {counts['passed']} | {counts['failed']} | {rate:.0f}% |\n")
        
        log_file.write("\n## Failed Tests\n\n")
        for r in results:
            if not r["passed"]:
                log_file.write(f"- **{r['id']}**: {r['category']} - {r['question'][:50]}...\n")
                for refl in r["reflections"]:
                    if refl.startswith("❌"):
                        log_file.write(f"  - {refl}\n")
        
        log_file.write("\n## Overall Reflections\n\n")
        log_file.write("*To be filled in manually after reviewing results*\n\n")
    
    print("\n" + "="*70)
    print("TEST SUITE COMPLETE")
    print("="*70)
    print(f"Results logged to: {log_filename}")
    print(f"Passed: {passed}/{len(results)} ({100*passed/len(results):.1f}%)")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
