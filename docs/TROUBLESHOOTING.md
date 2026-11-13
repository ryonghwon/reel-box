# Troubleshooting

## Mac blocks the application

Mac packages are ad-hoc signed for integrity but are not notarized by Apple. For a warning that Apple cannot verify the developer, confirm the download source and checksum. If you choose to allow the app, use **System Settings > Privacy & Security > Open Anyway**, following [Apple's instructions](https://support.apple.com/en-us/102445).

If macOS says the app is **damaged**, download the full archive again and replace the app bundle. Keep your library, download folders, and app-data directory. Report persistent failures with the package name and macOS version. Do not disable Gatekeeper or system-wide security settings.

## The app stays on Connecting

Restart Reel Box. Startup failures are recorded in `logs/desktop.log` inside the app-data directory. If required runtime files are missing, reinstall the complete app package. Reinstalling does not require deleting the library’s data directory.

For Docker, run `docker compose ps` and inspect the `api`, `worker`, `maintenance`, and `redis` logs. The web service and API must use the same `API_TOKEN`. Keep all queue services running while downloads are active.

## An item failed to download

Select the item and read the error in **Details**. The error code identifies which action is useful:

| Error or condition | What to do |
| --- | --- |
| Sign-in, age verification, or audience restriction | For Instagram, open the item in the app’s Instagram window and complete the required verification with your account. Retry only if the post opens normally. |
| `RATE_LIMITED` | Wait until the resume time shown in the app. Repeatedly adding the same URLs does not remove the platform limit. |
| `UNAVAILABLE` | Open the source URL to check whether the post still exists and is accessible. |
| `NETWORK_ERROR` | Restore the connection, then retry the failed item. |
| `DISK_FULL` | Free space on the destination drive. |
| `STORAGE_UNAVAILABLE` | Reconnect the drive and check folder permissions. |
| `SIZE_LIMIT` | Check the file-size limit. For video, consider a lower available resolution. |
| `NO_MEDIA` | Check that the post contains media supported by the selected download mode. |
| `DRM_PROTECTED` | This media cannot be downloaded by Reel Box. |

The Instagram window has its own session. Signing in in Chrome or Safari does not connect that session to Reel Box. For Vimeo and other platforms that require unsupported authentication, use the original site’s download option when available.

## Import complete, but the list is still visible

The import screen retains its summary and progress so an interrupted list can be resumed. **Import another file** clears that screen while keeping items already added to the library. Import completion means the links were registered; individual downloads may still be running.

If the task limit is reached, the remaining links stay available to resume or export. Deleting a task also deletes its managed files. Save any copies you need before removing records, or adjust the configured `MAX_JOBS` limit within its supported range.

## There are more library items than source links

A post may contain several videos and an image group. Those attachments share a source URL but can appear as separate library items. Compare the source-link count with the item’s attachment information before deleting what looks like a duplicate.

A signed-in Instagram save is linked to an existing record when the source and attachment can be matched. If several different attachments are present, the app keeps them distinct.

## A saved file cannot be found

Check that its drive is connected. Changing the download folder affects newly added items; earlier files remain at their previous locations. If a file was moved manually, restore it to the recorded location.

If auto-delete is enabled, check the expiry date. Expired files can be removed while their records remain visible. Copies saved outside the managed library are not removed by this setting.

## A recording has no sound

Check whether the system sharing dialog offers audio for the selected tab, window, or screen. Availability varies by operating system and source. Record and play a short segment before capturing the full clip. A protected video may appear black; recording does not remove DRM restrictions.

## Report a problem

Include the app version, operating system, error code, and steps needed to reproduce the issue. Remove account information and personal paths from logs. Do not attach sign-in data, account export archives, private library contents, or private post URLs to a public issue.
