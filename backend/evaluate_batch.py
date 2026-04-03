import os
import subprocess
import json
import argparse
import pandas as pd

def run_evaluation(video_path, gt_path, model='yolo11n.pt'):
    """
    Runs evaluate_vision.py and parses the output.
    Returns a dictionary of metrics.
    """
    cmd = [
        "python3", "backend/evaluate_vision.py",
        "--video", video_path,
        "--model", model
    ]
    if gt_path and os.path.exists(gt_path):
        cmd.extend(["--gt", gt_path])
    
    # We might need to modify evaluate_vision.py to output JSON or just parse stdout
    # For now, let's assume we capture stdout and parse it
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout
        
        metrics = {
            "Video": os.path.basename(video_path),
            "Status": "Success"
        }
        
        # Simple parsing logic (looking for keys in stdout)
        for line in output.split('\n'):
            if "PRECISIÓN:" in line:
                metrics["Precision"] = line.split(':')[-1].strip()
            if "RECALL:" in line:
                metrics["Recall"] = line.split(':')[-1].strip()
            if "F1 SCORE:" in line:
                metrics["F1 Score"] = line.split(':')[-1].strip()
            if "Total True Positives (TP):" in line:
                metrics["TP"] = line.split(':')[-1].strip()
            if "Total False Positives (FP):" in line:
                metrics["FP"] = line.split(':')[-1].strip()
            if "Total False Negatives (FN):" in line:
                metrics["FN"] = line.split(':')[-1].strip()
        
        return metrics
    except subprocess.CalledProcessError as e:
        print(f"Error evaluating {video_path}: {e.stderr}")
        return {"Video": os.path.basename(video_path), "Status": "Error", "Error": e.stderr}

def main():
    parser = argparse.ArgumentParser(description="Batch Evaluation for Vision Layer (3.1)")
    parser.add_argument('--dir', type=str, required=True, help="Directorio con videos de prueba")
    parser.add_argument('--gt-dir', type=str, help="Directorio con archivos GT (misma base que el video)")
    parser.add_argument('--model', type=str, default='yolo11n.pt')
    parser.add_argument('--output-md', type=str, default='vision_metrics_table.md', help="Nombre del archivo MD para la tabla")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"Error: {args.dir} no es un directorio.")
        return

    video_files = [f for f in os.listdir(args.dir) if f.endswith(('.mp4', '.avi', '.mov'))]
    all_metrics = []

    print(f"Iniciando evaluación por lotes de {len(video_files)} videos...")

    for video_file in video_files:
        video_path = os.path.join(args.dir, video_file)
        
        # Search for GT file
        gt_base = os.path.splitext(video_file)[0]
        gt_path = None
        if args.gt_dir:
            potential_gt = os.path.join(args.gt_dir, f"{gt_base}.txt")
            if os.path.exists(potential_gt):
                gt_path = potential_gt
        
        print(f"Evaluando: {video_file}...")
        metrics = run_evaluation(video_path, gt_path, args.model)
        all_metrics.append(metrics)

    # Create Table
    df = pd.DataFrame(all_metrics)
    
    # Format markdown table
    md_table = df.to_markdown(index=False)
    
    with open(args.output_md, 'w') as f:
        f.write("# Tabla de Métricas de Evaluación - Capa de Visión (3.1)\n\n")
        f.write(md_table)
        f.write("\n\n*Generado automáticamente por evaluate_batch.py*")

    print(f"\nGenerada tabla de métricas en: {args.output_md}")
    print(md_table)

if __name__ == '__main__':
    main()
