<task>
  <problem>situation or deficiency motivating the task</problem>

  <objective>transformation or analysis to perform</objective>

  <stakes>...</stakes>

  <context>
    <workflow>...</workflow>
    <stage>...</stage>
    <consumes>...</consumes>
    <produces>...</produces>
  </context>

  <inputs>
    <artifact_type>...</artifact_type>
    <input_contract>path to an external file</input_contract>
    <assumptions>...</assumptions>
    <known_limits>...</known_limits>
  </inputs>

  <outputs>
    <format>...</format>
    <output_contract>path to an external file</output_contract>
    <output_path>...</output_path>
    <naming_convention>...</naming_convention>
  </outputs>

  <resources>
    <tools>...</tools>
    <permissions>...</permissions>
  </resources>

  <procedure mode="required | recommended | heuristic">
    <step>...</step>
  </procedure>

  <success_conditions>
    <condition>...</condition>
  </success_conditions>

</task>
