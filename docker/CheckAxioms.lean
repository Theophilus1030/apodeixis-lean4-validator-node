import Lean
import ValidatorProject

open Lean Meta

/-- 核心检测逻辑 -/
def containsSorry (e : Expr) : Bool :=
  Option.isSome <| e.find? fun t =>
    t.isConstOf ``sorryAx

def checkAxioms : MetaM Unit := do
  let env ← getEnv
  let mut cheatDetected := false

  -- 1. 找到 ValidatorProject 模块在环境中的 ID
  -- 因为 ValidatorProject 是被 import 进来的，它一定有一个 Module Index
  let targetModuleName : Name := `ValidatorProject
  let modIdx? := env.header.moduleNames.findIdx? (· == targetModuleName)

  match modIdx? with
  | none =>
      -- 如果找不到这个模块，说明环境加载有问题
      IO.println "⚠️ 警告: 无法在环境中定位 ValidatorProject 模块，检查可能不完整。"
  | some targetIdx =>
      IO.println s!"🔍 Locking on module: {targetModuleName} (Idx: {targetIdx})"
      IO.println "🔍 Scanning for sorries..."

      -- 2. 遍历所有常量
      for (name, cinfo) in env.constants.toList do

        -- 3. [关键修复] 只检查属于该模块的常量
        -- getModuleIdxFor? 返回常量的来源。必须严格匹配 ValidatorProject 的 ID。
        -- 这样就完美排除了 CheckAxioms 自身 (Local) 和 Mathlib (Other Imports)
        let belongsToUserCode := match env.getModuleIdxFor? name with
          | some idx => idx.toNat == targetIdx
          | none => false

        if belongsToUserCode then
          -- 检查 A: 证明体 (Value)
          match cinfo.value? with
          | some val =>
              if containsSorry val then
                 IO.println s!"🚨 [CHEAT_DETECTED] '{name}' 的证明使用了 'sorry'!"
                 cheatDetected := true
          | none => pure ()

          -- 检查 B: 类型定义 (Type)
          if containsSorry cinfo.type then
              IO.println s!"🚨 [CHEAT_DETECTED] '{name}' 的类型依赖 'sorry'!"
              cheatDetected := true

          -- 检查 C: 自定义公理 (Axiom)
          -- 只要是用户模块里的 Axiom，一律视为作弊 (因为用户只应该写 theorem/def)
          match cinfo with
          | ConstantInfo.axiomInfo _ =>
              IO.println s!"🚨 [CHEAT_DETECTED] 发现自定义公理: {name}"
              cheatDetected := true
          | _ => pure ()

  if cheatDetected then
    IO.println "❌ VERIFICATION_FAILED"
  else
    IO.println "✅ VERIFICATION_PASSED"

#eval! checkAxioms
