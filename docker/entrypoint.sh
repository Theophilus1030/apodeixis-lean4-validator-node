import Lean
import ValidatorProject

open Lean Meta

/-- Core detection logic -/
def containsSorry (e : Expr) : Bool :=
  Option.isSome <| e.find? fun t => 
    t.isConstOf ``sorryAx

def checkAxioms : MetaM Unit := do
  let env ← getEnv
  let mut cheatDetected := false
  
  -- 1. Find the ID of the ValidatorProject module in the environment
  -- Since ValidatorProject is imported, it must have a Module Index
  let targetModuleName : Name := `ValidatorProject
  let modIdx? := env.header.moduleNames.findIdx? (· == targetModuleName)

  match modIdx? with
  | none => 
      -- If the module cannot be found, it indicates an issue with environment loading
      IO.println "⚠️ Warning: Unable to locate ValidatorProject module in the environment. Check might be incomplete."
  | some targetIdx =>
      IO.println s!"🔍 Locking on module: {targetModuleName} (Idx: {targetIdx})"
      IO.println "🔍 Scanning for sorries..."

      -- 2. Iterate over all constants
      for (name, cinfo) in env.constants.toList do
        
        -- 3. [Critical Fix] Only check constants belonging to this module
        -- getModuleIdxFor? returns the source of the constant. It must strictly match the ValidatorProject ID.
        -- This perfectly excludes CheckAxioms itself (Local) and Mathlib (Other Imports).
        let belongsToUserCode := match env.getModuleIdxFor? name with
          | some idx => idx.toNat == targetIdx
          | none => false 

        if belongsToUserCode then
          -- Check A: Proof body (Value)
          match cinfo.value? with
          | some val => 
              if containsSorry val then
                 IO.println s!"🚨 [CHEAT_DETECTED] Proof of '{name}' uses 'sorry'!"
                 cheatDetected := true
          | none => pure ()

          -- Check B: Type definition (Type)
          if containsSorry cinfo.type then
              IO.println s!"🚨 [CHEAT_DETECTED] Type of '{name}' depends on 'sorry'!"
              cheatDetected := true

          -- Check C: Custom Axiom (Axiom)
          -- Any Axiom in the user module is considered cheating (users should only write theorem/def)
          match cinfo with
          | ConstantInfo.axiomInfo _ =>
              IO.println s!"🚨 [CHEAT_DETECTED] Custom axiom found: {name}"
              cheatDetected := true
          | _ => pure ()

  if cheatDetected then
    IO.println "❌ VERIFICATION_FAILED"
  else
    IO.println "✅ VERIFICATION_PASSED"

#eval! checkAxioms