# User guide

## Add links and review media

Select **Add links**, or press **Command+K** on Mac / **Ctrl+K** on Windows. Paste one post URL per line, choose a download mode, and select **Check links**. Each link is checked before a download starts, so you can review the title, preview, and available resolutions.

**Detect media type** finds video and image attachments. **Audio only** extracts audio from supported videos. Matching platform, URL, and download-mode combinations are not added twice.

YouTube playlists and channels require **Import playlists and channels** in the Add links dialog. Set an entry limit of up to 100. An individual video link still adds only that video; a playlist or channel adds entries up to the chosen limit.

## Choose format and quality

MP4 is the default video format. Select an item marked **Ready to download** and use the **Details** panel to choose **Best available** or one of its detected resolutions. Quality cannot be changed after that item has started downloading.

MP4 output keeps the selected resolution and uses H.264/AAC conversion when needed for compatibility. **Original format** avoids re-encoding. A format that downloads successfully may still require an external player if the app’s preview cannot decode it.

For a completed video, **Create compatible MP4** creates a separate H.264/AAC copy at up to 720p. The original file stays in the library. This command is distinct from choosing full-resolution MP4 before downloading.

## Understand posts, groups, and files

A source link can contain more than one attachment. Reel Box groups images from the same post into one library item and displays videos as individual items. The source-link count, visible-item count, and file count can therefore differ without indicating duplicate downloads.

Select an image group to browse its attachments in the Details panel. Open **Files** to see the actual saved files. Selecting a group for export or deletion includes its members; deleting the current image from the detail panel targets that image only.

## Import Instagram saved posts

Request an export in Instagram’s Accounts Center that includes **Saved**, preferably in JSON format with the full date range. When Instagram finishes preparing it, download the export to your device.

1. Open **Instagram saved posts** in Reel Box.
2. Select the ZIP, `saved_posts.json`, saved-posts HTML, or saved-collections file.
3. Review the detected links and duplicates.
4. Leave **Download imported media automatically** on to download after checking, or turn it off to review previews first.
5. Select **Import and download** or **Import list**.

Files can be up to 32 MB. For a larger archive, extract it and select only the saved-posts file. Reel Box reads the post URLs; the archive does not itself contain all the media you saved on Instagram. The original export archive is not retained by the app.

Links and import progress are saved locally. **Pause import** stops adding new links while items already in the queue continue processing. Reopen the import screen to resume the remaining list. After completion, **Import another file** clears the import screen without deleting library items or downloaded files.

## Save posts that require Instagram sign-in

For an Instagram item that needs authentication, select **Open in Instagram to save**. Sign in directly on Instagram’s official page inside the app, complete any verification, and open the post.

For a single item, play the video or display the image, select **Check visible media**, then choose the matching media and save it. For several failed items, select them in the library and choose **Retry with Instagram**. The app can pass up to 500 items to this workflow. Use **Start batch** or **Continue batch** in the Instagram window.

The batch pauses when sign-in, additional verification, or access review is needed. Complete the step yourself, then continue. Sign-in does not guarantee access to every post, and it does not automatically retry every failure in the library.

The app’s Instagram session is separate from Chrome, Safari, and other browsers. Saved media is associated with its source URL. Where the attachment can be matched, a successful result updates the existing failed item instead of leaving another copy of the same record.

## Browse and export

Search by title, creator, or URL. Use the platform sidebar and status tabs to narrow the library, and switch between cards, compact thumbnails, or a list. Scrolling loads more items. **Select loaded items** selects the cards currently loaded, not every item that might match the filter.

With a selection, ZIP, CSV, download, and delete actions apply to that selection. Without a selection, those actions use the current search and filter results. Only completed files can be included in an export.

**Save a copy** writes an individual file elsewhere. A ZIP export includes media files and `manifest.csv`. The CSV records source URLs, titles, creators, status, filenames, sizes, and dates. Copies exported outside the library are not managed by the app’s auto-delete setting.

**Delete selected** and **Delete results** remove records and their saved files. Active tasks are skipped. To keep a file after removing its library record, save a copy first.

## Record a screen

Open **Screen recorder**, choose a source in the system sharing dialog, and include audio if that option is available. Play the segment you need, then stop recording and review the preview. Save it as MP4 to add the converted file to the library, or save the original recording directly.

Recording stops after 10 minutes or 256 MB. The library MP4 is converted to up to 720p at 30 fps. You can also import an existing WebM or MP4 recording of up to 512 MB. Audio capture depends on the operating system and selected source. Test a short segment before recording a long clip.
