# Read a private image with the built-in Windows OCR engine. No UI or input.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$awaitMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1 -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Ocr($Operation, $ResultType) {
    $task = $awaitMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    $task.Result
}
function New-OcrEngine {
    # The game text is English. Windows only ships OCR for the languages
    # installed on the PC, so a Portuguese or Spanish Windows may have no en-US
    # recognizer. Prefer en-US, then any English, then any Latin-script
    # recognizer (it reads "Buy", "Cancel" and prices; the caller's strict
    # matching refuses anything it misreads).
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
    if ($null -ne $engine) { return $engine }
    $available = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages)
    $ordered = @($available | Where-Object { $_.LanguageTag -like 'en*' }) +
               @($available | Where-Object { $_.LanguageTag -notlike 'en*' -and $_.Script -eq 'Latn' })
    foreach ($language in $ordered) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
        if ($null -ne $engine) { return $engine }
    }
    $installed = ($available | ForEach-Object { $_.LanguageTag }) -join ', '
    if (-not $installed) { $installed = 'none' }
    throw "English Windows OCR is not installed (OCR languages: $installed). Add English in Settings > Time & language > Language & region, then restart the app"
}
# Keep the reason: the persistent mode reports it per request instead of exiting silently.
$engine = $null; $engineError = $null
try { $engine = New-OcrEngine } catch { $engineError = "$_" }
function Read-Frame($Path) {
    if ($null -ne $engineError) { throw $engineError }
    $file = Await-Ocr ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
    $stream = Await-Ocr ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Await-Ocr ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-Ocr ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result = Await-Ocr ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $words = @($result.Lines | ForEach-Object {
                $_.Words | ForEach-Object {
                    @{ text = $_.Text; box = @($_.BoundingRect.X, $_.BoundingRect.Y,
                        ($_.BoundingRect.X + $_.BoundingRect.Width), ($_.BoundingRect.Y + $_.BoundingRect.Height)) }
                }
            })
            # Word bounds follow the detected text angle; report it so callers can
            # map them back to image coordinates.
            @{ text = $result.Text; angle = $result.TextAngle; words = $words } | ConvertTo-Json -Compress -Depth 5
        }
        finally { $bitmap.Dispose() }
    }
    finally { $stream.Dispose() }
}
if ($env:E7_MOUSE_OCR_SERVE -eq '1') {
    # Persistent mode: one image path per stdin line, one JSON line back, until
    # stdin closes. Saves PowerShell and WinRT start-up on every read.
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        try { $reply = Read-Frame $line }
        catch { $reply = @{ error = "$_" } | ConvertTo-Json -Compress }
        [Console]::Out.WriteLine($reply)
        [Console]::Out.Flush()
    }
}
else {
    Read-Frame $env:E7_MOUSE_OCR_FRAME
}
