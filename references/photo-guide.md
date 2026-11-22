# Photo guide: shots that can be measured

Send this to the maker (or read it out) before they photograph a part, or as soon as `photo_tools.py info` flags a problem. Each line fixes a problem the first project actually had.

## The shot list

1. **Send the originals.** AirDrop, or share/email with "Actual Size", or copy off the phone. Not screenshots, not through a messaging app: those shrink a 4000-pixel photo to 1500 and strip the details that tell raised from cut-in. iPhones save originals as HEIC, which the kit can't read unless `pillow-heif` is installed: set Settings > Camera > Formats to Most Compatible before shooting, or convert on a Mac with `sips -s format jpeg photo.heic --out photo.jpg`.
2. **All six sides,** straight on: top, bottom, both long sides, both ends. Plus two angled "three-quarter" shots. Every side that isn't photographed becomes a guess, and guesses get built wrong.
3. **Ruler at the same height as the face you're photographing.** Prop the ruler (or the caliper's scale) on something so it's level with that face, right beside the part. A face sitting above the ruler reads too big by about its height divided by the camera's distance: 10 mm above the ruler at 15 cm is about 7%, at 30 cm about 3%. (This is the one place that rule of thumb is written down; other files point here.)
4. **Step back and zoom.** Use the 2x or 3x lens from 20 to 30 cm instead of the 1x lens up close. Close-up wide shots bend the edges and make near faces look bigger than far ones.
5. **Fill the frame with the part and the ruler,** sharp focus on the part. Tap to focus on it.
6. **Soft light for the measuring shots,** plus **one extra shot of each detailed face lit from one side** (a desk lamp low and to the left, room light off). Side light throws shadows that show which details stand up and which are cut in. Note which side the lamp was on.
7. **Mark the ends.** Stick a small label ("A") on one end, so every photo shows which end is which. Without it, features that are only on one end can't be matched up between photos.
8. **Caliper readings, photographed.** Overall length, width and height, plus anything that has to fit (a hole, a slot, a pin). One photo of the caliper reading each time, or just type the numbers.
9. **If something passes through or attaches,** photograph that too (the disc, the axle, the mounting point), or measure it.

## Naming

Put them in the project's `reference/` folder as `photo-1-top.jpg`, `photo-2-bottom.jpg`, `photo-3-left.jpg` ... (JPEG or PNG) and keep the originals untouched. Crops and annotated copies go in `questions/`.
