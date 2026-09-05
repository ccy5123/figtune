Attribute VB_Name = "FigTune"
' =====================================================================
'  figtune PowerPoint add-in  (VBA / .ppam)
'
'  IguanaTeX와 같은 구조: 그림과 함께 그것을 만든 소스를 도형에 심어두고,
'  도형을 선택해 다시 편집한다. 소스는 도형의 alt text에 들어가므로
'  프레젠테이션을 옮겨도 따라다닌다.
'
'  ── 시험되지 않은 코드 ────────────────────────────────────────────
'  이 모듈은 리눅스 환경에서 작성되어 PowerPoint에서 실행 검증된 적이
'  없습니다. 파이썬 쪽(figtune render / edit / refresh)은 테스트를
'  통과했지만, 아래 VBA는 Windows PowerPoint에서 직접 돌려보며 다듬어야
'  합니다. 특히 Shell 대기 처리와 경로 인용(quoting)을 확인하세요.
'  ──────────────────────────────────────────────────────────────────
'
'  설치
'    1. 이 파일을 .pptm에 임포트한 뒤 .ppam으로 "다른 이름으로 저장"
'    2. 파일 > 옵션 > 추가 기능 > PowerPoint 추가 기능 > 이동 > 새로 추가
'    3. FigTuneSettings에서 python 경로와 임시 폴더를 지정
' =====================================================================

Option Explicit

Private Const MARK_OPEN As String = "<figtune:1>"
Private Const MARK_CLOSE As String = "</figtune>"

' --- 설정 ------------------------------------------------------------

Private Function PythonPath() As String
    PythonPath = GetSetting("figtune", "config", "python", "")
    If PythonPath = "" Then PythonPath = "python"
End Function

Private Function TempDir() As String
    TempDir = GetSetting("figtune", "config", "tempdir", "")
    If TempDir = "" Then TempDir = Environ$("TEMP")
End Function

Private Function DefaultDPI() As Long
    DefaultDPI = CLng(GetSetting("figtune", "config", "dpi", "300"))
End Function

Public Sub FigTuneSettings()
    Dim p As String, t As String, d As String
    p = InputBox("python 실행 파일 경로" & vbCrLf & _
                 "(분석 환경의 venv를 지정하세요)", "figtune", PythonPath())
    If p <> "" Then SaveSetting "figtune", "config", "python", p
    t = InputBox("임시 폴더", "figtune", TempDir())
    If t <> "" Then SaveSetting "figtune", "config", "tempdir", t
    d = InputBox("기본 출력 DPI", "figtune", CStr(DefaultDPI()))
    If d <> "" Then SaveSetting "figtune", "config", "dpi", d
End Sub

' --- 유틸 ------------------------------------------------------------

Private Function Q(ByVal s As String) As String
    Q = """" & s & """"
End Function

' 명령을 실행하고 끝날 때까지 기다린다. 종료 코드를 돌려준다.
Private Function RunWait(ByVal cmd As String) As Long
    Dim sh As Object
    Set sh = CreateObject("WScript.Shell")
    RunWait = sh.Run(cmd, 1, True)
End Function

Private Function IsFigTuneShape(ByVal shp As Shape) As Boolean
    On Error Resume Next
    IsFigTuneShape = (InStr(shp.AlternativeText, MARK_OPEN) > 0)
End Function

Private Function SelectedFigure() As Shape
    Dim shp As Shape
    If ActiveWindow.Selection.Type <> ppSelectionShapes Then
        MsgBox "figtune 그림을 먼저 선택하세요.", vbExclamation, "figtune"
        Exit Function
    End If
    Set shp = ActiveWindow.Selection.ShapeRange(1)
    If Not IsFigTuneShape(shp) Then
        MsgBox "선택한 도형에는 figtune 소스가 없습니다.", vbExclamation, "figtune"
        Exit Function
    End If
    Set SelectedFigure = shp
End Function

' --- 새 그림 삽입 ----------------------------------------------------

Public Sub NewFigure()
    Dim scriptPath As String, tmp As String, pngPath As String, specPath As String
    Dim rc As Long, shp As Shape

    scriptPath = PickPythonScript()
    If scriptPath = "" Then Exit Sub

    tmp = TempDir()
    pngPath = tmp & "\figtune_" & Format(Now, "hhnnss") & ".png"
    specPath = Replace(pngPath, ".png", ".yaml")

    ' GUI를 띄워 사용자가 다듬게 하고, 결과를 png/spec으로 회수한다
    rc = RunWait(Q(PythonPath()) & " -m figtune.cli edit " & Q(scriptPath) & _
                 " --png-out " & Q(pngPath) & " --spec-out " & Q(specPath) & _
                 " --dpi " & DefaultDPI())
    If rc <> 0 Or Dir(pngPath) = "" Then
        MsgBox "figtune이 그림을 만들지 못했습니다.", vbCritical, "figtune"
        Exit Sub
    End If

    Set shp = ActiveWindow.View.Slide.Shapes.AddPicture( _
        pngPath, msoFalse, msoCTrue, 100, 100)
    shp.AlternativeText = BuildAltText(scriptPath, specPath)
    shp.Select
End Sub

' --- 기존 그림 편집 --------------------------------------------------

Public Sub EditFigure()
    Dim shp As Shape, scriptPath As String, specPath As String, pngPath As String
    Dim rc As Long, newShp As Shape
    Dim L As Single, T As Single, W As Single, H As Single, R As Single
    Dim z As Long

    Set shp = SelectedFigure()
    If shp Is Nothing Then Exit Sub

    scriptPath = ExtractScriptPath(shp)
    If Dir(scriptPath) = "" Then
        MsgBox "원본 스크립트를 찾을 수 없습니다:" & vbCrLf & scriptPath, _
               vbCritical, "figtune"
        Exit Sub
    End If

    specPath = TempDir() & "\figtune_edit.yaml"
    pngPath = TempDir() & "\figtune_edit.png"
    WriteSpecToFile shp, specPath

    rc = RunWait(Q(PythonPath()) & " -m figtune.cli edit " & Q(scriptPath) & _
                 " --spec-in " & Q(specPath) & " --spec-out " & Q(specPath) & _
                 " --png-out " & Q(pngPath) & " --dpi " & DefaultDPI())
    If rc <> 0 Or Dir(pngPath) = "" Then Exit Sub

    ' 배치를 보존한 채 갈아끼운다. 발표자가 맞춰둔 위치를 잃으면 안 된다.
    L = shp.Left: T = shp.Top: W = shp.Width: H = shp.Height
    R = shp.Rotation: z = shp.ZOrderPosition

    Set newShp = ActiveWindow.View.Slide.Shapes.AddPicture( _
        pngPath, msoFalse, msoCTrue, L, T, W, H)
    newShp.Rotation = R
    newShp.AlternativeText = BuildAltText(scriptPath, specPath)
    shp.Delete
    Do While newShp.ZOrderPosition > z
        newShp.ZOrder msoSendBackward
    Loop
    newShp.Select
End Sub

' --- 덱 전체 갱신 ----------------------------------------------------
'  데이터나 모델이 바뀌었을 때 모든 그림을 한 번에 다시 만든다.
'  figtune이 PowerPoint에 붙어야 하는 진짜 이유.

Public Sub RefreshDeck()
    Dim deck As String, rc As Long
    If ActivePresentation.Path = "" Then
        MsgBox "먼저 프레젠테이션을 저장하세요.", vbExclamation, "figtune"
        Exit Sub
    End If
    ActivePresentation.Save
    deck = ActivePresentation.FullName

    rc = RunWait(Q(PythonPath()) & " -m figtune.cli refresh " & Q(deck))
    If rc <> 0 Then
        MsgBox "일부 그림을 갱신하지 못했습니다. 콘솔 출력을 확인하세요.", _
               vbExclamation, "figtune"
    End If
    MsgBox "갱신이 끝났습니다. 파일을 닫았다가 다시 여세요.", _
           vbInformation, "figtune"
End Sub

' --- payload 처리 ----------------------------------------------------
'  파이썬 쪽 figtune.office.pptx_link 와 형식이 반드시 일치해야 한다.
'  payload = base64(zlib(json))  안에 script / dpi / spec(YAML 문자열)
'
'  주의: VBA에는 zlib이 없다. 압축·해제는 파이썬 헬퍼에 위임하는 것이
'  가장 확실하다. 아래 두 함수는 그 위임 지점이며, 구현 시
'  `python -m figtune.office.vba_bridge pack/unpack` 같은 보조 명령을
'  추가하는 편이 VBA에서 직접 다루는 것보다 훨씬 안전하다.

Private Function BuildAltText(ByVal scriptPath As String, _
                              ByVal specPath As String) As String
    Dim tmpOut As String
    tmpOut = TempDir() & "\figtune_alt.txt"
    RunWait Q(PythonPath()) & " -m figtune.office.vba_bridge pack" & _
            " --script " & Q(scriptPath) & " --spec " & Q(specPath) & _
            " --dpi " & DefaultDPI() & " --out " & Q(tmpOut)
    BuildAltText = ReadTextFile(tmpOut)
End Function

Private Sub WriteSpecToFile(ByVal shp As Shape, ByVal specPath As String)
    Dim altPath As String
    altPath = TempDir() & "\figtune_alt_in.txt"
    WriteTextFile altPath, shp.AlternativeText
    RunWait Q(PythonPath()) & " -m figtune.office.vba_bridge unpack" & _
            " --alt " & Q(altPath) & " --spec-out " & Q(specPath)
End Sub

Private Function ExtractScriptPath(ByVal shp As Shape) As String
    Dim altPath As String, outPath As String
    altPath = TempDir() & "\figtune_alt_in.txt"
    outPath = TempDir() & "\figtune_script.txt"
    WriteTextFile altPath, shp.AlternativeText
    RunWait Q(PythonPath()) & " -m figtune.office.vba_bridge unpack" & _
            " --alt " & Q(altPath) & " --script-out " & Q(outPath)
    ExtractScriptPath = Trim(ReadTextFile(outPath))
End Function

' --- 파일 입출력 -----------------------------------------------------

Private Function ReadTextFile(ByVal path As String) As String
    Dim fso As Object, ts As Object
    If Dir(path) = "" Then Exit Function
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set ts = fso.OpenTextFile(path, 1, False, -1)   ' -1 = Unicode
    If Not ts.AtEndOfStream Then ReadTextFile = ts.ReadAll
    ts.Close
End Function

Private Sub WriteTextFile(ByVal path As String, ByVal content As String)
    Dim fso As Object, ts As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set ts = fso.CreateTextFile(path, True, True)   ' True = Unicode
    ts.Write content
    ts.Close
End Sub

Private Function PickPythonScript() As String
    Dim fd As FileDialog
    Set fd = Application.FileDialog(msoFileDialogFilePicker)
    fd.Title = "플로팅 스크립트 선택"
    fd.Filters.Clear
    fd.Filters.Add "Python", "*.py"
    fd.AllowMultiSelect = False
    If fd.Show = -1 Then PickPythonScript = fd.SelectedItems(1)
End Function
