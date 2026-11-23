# Validation record · 5 November 2026

The completed reference used actual captured Sentinel-2 Collection 1 red/NIR AOI subsets from 4, 5 and 10 June 2025. Six requests completed on native grids. All six outputs had finite coverage above 96%, zero values outside the nominal NDVI interval, and cloud screening explicitly unassessed. Those observations do not establish clear sky suitability.

Sixteen end to end checks passed: membership before attempts; read only planning; six published products; reuse without new attempts; partial restart; missing input recovery; abrupt worker interruption and reconciliation; abrupt coordinator death; missing output recovery with preserved success; multiple locations and corruption; receipt identity/checksum rejection; frozen membership and runtime relocation; changed scientific identity; persistent execution budgets; exclusive coordinator lock; and a saved report with a consistent snapshot.

The completed new schema and all three repair checks passed. The unmodified student edition failed all four groups as intended, and setup left no partially created workspace when its schema was unfinished.

Every code cell in the completed student and instructor notebooks executed twice, first from a clean local workspace and then against the existing workspace. These were IPython cell executions. An attempted Jupyter kernel startup was blocked by local socket restrictions. JupyterLab GUI behavior was not verified.

The report contact sheet was visually inspected; report anchor links were checked programmatically. Browser layout, Windows file locking and Gaia deployment were not verified. The execution design remains serial.

The C1 overlays passed the existing Lab 3 and Lab 4 checks with completed reference schemas/repairs. Lab 3 init/plan and a live red/NIR acquisition/verification succeeded with the C1 config. The updated Lab 4 demo published NDVI using the C1 metadata scale/offset. The full older notebooks were not executed for these overlays.

A background scratch file synchronizer restored deliberately moved files during an initial fault test. Final fault and notebook checks used isolated local directories without that synchronizer. The README specifies a local workspace for these drills.

Runtime: Python 3.12.14; NumPy 2.3.5; Rasterio 1.5.2; GDAL 3.12.2; PROJ 9.8.1; PyYAML 6.0.3; Matplotlib 3.10.8; Linux. The supplied environment file describes supported dependencies; it is not a platform independent package lock.
