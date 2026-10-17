"""Retain rejected candidate, confirm restored source, and test baseline."""
import collections,json,pathlib,subprocess
import v020_integrity8 as a
R=a.R;O=a.O;C=O/'candidate1';B=O/'restored';B.mkdir()
m=json.loads((O/'manifest.json').read_text());cm=json.loads((C/'manifest.json').read_text())
p='android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt';t='android/app/src/test/kotlin/dev/opencaption/opencaption/E2eProtocolTest.kt'
assert a.sha(R/p)==m['files'][p]
old=json.loads((R/'evaluation/results/v020-round2/protocol/replay_manifest.json').read_text());assert a.sha(R/t)==old['product_source_files'][t]
# Retain exact candidate source separately; old immutable manifest refers to
# its historical source state, never current product after rejection.
guard='''        // Inspect the whole reply: pair extraction can discard a leading or
        // intermediate sentinel before validation of the selected fields.
        if (cleaned.contains("[NONE]", ignoreCase = true)) {
            return Result.Invalid("sentinel_mixed_with_subtitle")
        }
'''
s=(R/p).read_text().replace('        if (prefixedBalancedNone.matches(cleaned)) return Result.NoSpeech\n','        if (prefixedBalancedNone.matches(cleaned)) return Result.NoSpeech\n'+guard)
cp=C/'rejected-E2eProtocol.kt';cp.write_text(s);assert a.sha(cp)==cm['files'][p]
cpj=list(cm['compiler_files']);classes=B/'classes';classes.mkdir()
src=[p,'android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt',t,'evaluation/V020Integrity8.kt']
cmd=[a.J,'-Xmx256m','-cp',':'.join(cpj),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cpj[1:]),'-d',str(classes)]+[str(R/x) for x in src]
subprocess.run(cmd,check=True);runtime=str(classes)+':'+':'.join(cpj[1:]);subprocess.run([a.J,'-Xmx96m','-cp',runtime,'org.junit.runner.JUnitCore','dev.opencaption.opencaption.E2eProtocolTest'],check=True)
(B/'compile.json').write_text(json.dumps(dict(command=cmd,files={x:a.sha(R/x) for x in src},classes={str(x.relative_to(B)):a.sha(x) for x in classes.rglob('*.class')}),indent=2))
counts=collections.Counter();examples={}
for l in (O/'rows.jsonl').read_text().splitlines():
 r=json.loads(l)
 if not r['ignored_prefix'].strip():continue
 norm=lambda x:' '.join(x.strip().split())
 pfx=norm(r['ignored_prefix']);pair=r['pairs'][0]
 if pfx==norm(pair['english']):k='exact_english_echo'
 elif pfx==norm(pair['english']+'\n'+pair['chinese']):k='exact_unlabeled_pair_echo'
 elif '[NONE]' in pfx.upper():k='sentinel_preamble_compatible'
 else:k='unresolved_different_prefix'
 counts[k]+=1;examples.setdefault(k,[])
 if len(examples[k])<3:examples[k].append(dict(raw_sha256=r['raw_sha256'],raw=r['raw']))
verdict=dict(candidate_accepted=False,reason='Existing silencePreambleDoesNotEraseACompleteSpeechPair fails; no permission to erase last-complete-pair compatibility. Reject candidate and retain old test, not a new hallucination fix.',candidate_JUnit_passed=19,candidate_JUnit_total=20,restored_JUnit_passed=19,baseline_subtitles=940,candidate_subtitles=939,retained_product_subtitles=940,restored_protocol_sha=a.sha(R/'android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt'),restored_test_sha=a.sha(R/t),classification=dict(counts),examples=examples,new_model_requests=0,content_gain_verified=False,multiple_pairs_observed=0,proven_lost_correct_content=0,unresolved_prefix_truth_not_reassessed=True,old_apk_still_matches_product=True)
(O/'verdict.json').write_text(json.dumps(verdict,ensure_ascii=False,indent=2)+'\n');print(json.dumps(verdict,ensure_ascii=False,indent=2))
